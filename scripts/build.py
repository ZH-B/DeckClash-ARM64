#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decky-clash-arm64 构建器

把上游 chenx-dust/DeckyClash 的发布包改造成可在 ARM64（Armada OS 等）上
运行的 Decky 插件包。

为什么要做这个
--------------
上游把内核下载地址写死成 mihomo-linux-amd64-<ver>.gz：

    py_modules/upgrade.py:166,168
    install.sh:213

在 ARM64 机器上就会装上一个 x86-64 内核。它靠 binfmt_misc + qemu-x86_64
模拟执行，Go 运行时的 CPU 特征探测（klauspost/cpuid）和包初始化
（gopacket/layers.init）在 QEMU 下会 SIGSEGV，于是：

    mihomo -t 崩溃 -> check_config 返回 False -> 导入订阅报 "Invalid config"

本脚本做三件事（插件里只有 bin/mihomo 与架构绑定，其余都是 Python/JS）：

  1. upgrade.py：写死的 amd64 改成运行时 platform.machine() 探测
  2. install.sh：同样处理（如果包里有）
  3. bin/mihomo：换成目标架构的二进制
  4. 可选：重命名插件身份，便于作为独立项目发布

用法
----
# 从官方包出发，出 ARM64 独立版
python3 build.py \
    --src  DeckyClash-full.zip \
    --core mihomo-linux-arm64-v1.19.31.gz \
    --out  DeckyClash-ARM64.zip

# 只重命名（源包内核已经是 arm64 时）
python3 build.py --src DeckyClash-arm64.zip --out DeckyClash-ARM64.zip \
    --rename "Decky Clash ARM64"

# 保持上游身份（覆盖安装，设置/订阅延续）
python3 build.py --src ... --core ... --out ... --drop-in
"""

import argparse
import gzip
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

# uname -m -> mihomo 资产后缀
ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "armv7l": "armv7", "armv7": "armv7",
    "armv6l": "armv6", "armv6": "armv6",
    "i386": "386", "i486": "386", "i586": "386", "i686": "386",
    "riscv64": "riscv64",
    "ppc64le": "ppc64le",
    "s390x": "s390x",
    "loongarch64": "loong64-abi2",
}

PY_HELPER = '''def _detect_core_arch() -> str:
    """按本机 CPU 架构选择 mihomo 资产后缀（上游写死了 amd64）。"""
    import platform
    _m = platform.machine().lower()
    return {
        "x86_64": "amd64", "amd64": "amd64",
        "aarch64": "arm64", "arm64": "arm64",
        "armv7l": "armv7", "armv7": "armv7",
        "armv6l": "armv6", "armv6": "armv6",
        "i386": "386", "i486": "386", "i586": "386", "i686": "386",
        "riscv64": "riscv64",
        "ppc64le": "ppc64le",
        "s390x": "s390x",
        "loongarch64": "loong64-abi2",
    }.get(_m, _m)  # 未知架构沿用 uname 原值，宁可 404 也不静默装错架构


CORE_ARCH = _detect_core_arch()

'''

SH_CASE = r'''CORE_ARCH="$(uname -m)"
	case "${CORE_ARCH}" in
		x86_64|amd64)   CORE_ARCH=amd64 ;;
		aarch64|arm64)  CORE_ARCH=arm64 ;;
		armv7l|armv7)   CORE_ARCH=armv7 ;;
		armv6l|armv6)   CORE_ARCH=armv6 ;;
		i?86)           CORE_ARCH=386 ;;
		riscv64)        CORE_ARCH=riscv64 ;;
		ppc64le)        CORE_ARCH=ppc64le ;;
		s390x)          CORE_ARCH=s390x ;;
		loongarch64)    CORE_ARCH=loong64-abi2 ;;
		*)              ;; # 未知架构沿用 uname 原值，宁可 404 也不要装错
	esac'''


def log(m):
    print("  " + m)


def patch_py(path):
    src = open(path, encoding="utf-8").read()
    if "CORE_ARCH" in src:
        log("upgrade.py: 已打过补丁，跳过")
        return False
    if "mihomo-linux-amd64-" not in src:
        log("upgrade.py: 未找到 mihomo-linux-amd64-，跳过")
        return False
    anchor = "_URL_MAP: Dict[ResourceType, Callable[[str], str]] = {"
    src = src.replace("mihomo-linux-amd64-", "mihomo-linux-{CORE_ARCH}-")
    if anchor in src:
        src = src.replace(anchor, PY_HELPER + anchor, 1)
    open(path, "w", encoding="utf-8").write(src)
    log("upgrade.py: 内核地址 -> mihomo-linux-{CORE_ARCH}-（运行时探测）")
    return True


def patch_sh(path):
    src = open(path, encoding="utf-8").read()
    if "CORE_ARCH" in src:
        log("install.sh: 已打过补丁，跳过")
        return False
    pat = re.compile(
        r'([ \t]*)RELEASE_URL="\$\{GITHUB_BASE_URL\}/MetaCubeX/mihomo/releases/download/'
        r'\$\{RELEASE_VERSION\}/mihomo-linux-amd64-\$\{RELEASE_VERSION\}\.gz"')
    if not pat.search(src):
        log("install.sh: 未匹配到内核下载行，跳过")
        return False
    src = pat.sub(lambda m: SH_CASE + "\n" + m.group(1) +
                  'RELEASE_URL="${GITHUB_BASE_URL}/MetaCubeX/mihomo/releases/download/'
                  '${RELEASE_VERSION}/mihomo-linux-${CORE_ARCH}-${RELEASE_VERSION}.gz"',
                  src, count=1)
    open(path, "w", encoding="utf-8").write(src)
    log("install.sh: 内核地址改为 ${CORE_ARCH}")
    return True


def rename_plugin(root, new_name, author=None):
    """改插件身份：目录名 + plugin.json + 前端面板标题。"""
    pj = os.path.join(root, "plugin.json")
    meta = json.load(open(pj, encoding="utf-8"))
    old_display = meta.get("name", "")
    meta["name"] = new_name
    if author:
        meta["author"] = author
    json.dump(meta, open(pj, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    log(f'plugin.json: name "{old_display}" -> "{new_name}"')

    # 上游 src/index.tsx:680 把面板标题写死成 "Decky Clash"，编译进 dist/index.js
    # 上游 src/index.tsx 把插件名/标题写死成 "Decky Clash"，编译进 dist/index.js。
    # 注意：definePlugin({ name }) 必须和 plugin.json 的 name 一致 ——
    # Decky 前端靠这个名字路由 RPC，不一致会导致面板打得开但拉不到任何数据
    # （表现为订阅列表为空）。所以这里做全量替换，而不是只改标题。
    dist = os.path.join(root, "dist", "index.js")
    if os.path.exists(dist) and old_display:
        s = open(dist, encoding="utf-8").read()
        n = 0
        for q in ('"', "'"):
            pat = f"{q}{old_display}{q}"
            n += s.count(pat)
            s = s.replace(pat, f"{q}{new_name}{q}")
        if n:
            open(dist, "w", encoding="utf-8").write(s)
            log(f'dist/index.js: 插件名/标题共 {n} 处 "{old_display}" -> "{new_name}"')
            left = s.count(f'"{old_display}"') + s.count(f"'{old_display}'")
            if left:
                log(f"  ⚠ 仍有 {left} 处旧名字残留，请检查")
        else:
            log("dist/index.js: 未找到旧插件名字符串，跳过")
    else:
        log("dist/index.js: 不存在，跳过（前端名字无法同步，面板可能拉不到数据）")
    return new_name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="上游 DeckyClash-full.zip / DeckyClash.zip")
    ap.add_argument("--core", help="目标架构的 mihomo（.gz 或裸二进制）；省略则保留包内原有内核")
    ap.add_argument("--out", required=True, help="输出 zip")
    ap.add_argument("--rename", default="Decky Clash ARM64",
                    help='新的插件显示名，默认 "Decky Clash ARM64"')
    ap.add_argument("--author", default=None, help="plugin.json 的 author")
    ap.add_argument("--drop-in", action="store_true",
                    help="保持上游身份（同名覆盖，设置与订阅延续）")
    ap.add_argument("--core-arch", default=None, help="仅用于打印提示")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.exit("源包不存在: " + args.src)
    if args.core and not os.path.exists(args.core):
        sys.exit("内核文件不存在: " + args.core)

    tmp = tempfile.mkdtemp(prefix="dcbuild-")
    try:
        print("[1/5] 解包源包")
        modes = {}
        with zipfile.ZipFile(args.src) as zf:
            zf.extractall(tmp)
            # Python 的 extractall 不还原权限位，这里自己记下来
            for i in zf.infolist():
                if i.filename.endswith("/"):
                    continue
                rel = i.filename.split("/", 1)[1] if "/" in i.filename else i.filename
                modes[rel] = (i.external_attr >> 16) & 0o7777
        root = None
        for d in sorted(os.listdir(tmp)):
            p = os.path.join(tmp, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "plugin.json")):
                root = p
                break
        if root is None:
            sys.exit("源包里找不到 plugin.json")
        orig_top = os.path.basename(root)
        log(f"插件根目录: {orig_top}/")

        print("[2/5] 修补架构写死问题")
        n = 0
        py = os.path.join(root, "py_modules", "upgrade.py")
        if os.path.exists(py):
            n += patch_py(py)
        else:
            log("没有 py_modules/upgrade.py")
        sh = os.path.join(root, "install.sh")
        if os.path.exists(sh):
            n += patch_sh(sh)
        else:
            log("包内无 install.sh（商店包正常如此）")
        if not n:
            log("没有产生新补丁（源包可能已经处理过）")

        print("[3/5] 处理内核")
        if args.core:
            bin_dir = os.path.join(root, "bin")
            os.makedirs(bin_dir, exist_ok=True)
            dst = os.path.join(bin_dir, "mihomo")
            old = os.path.getsize(dst) if os.path.exists(dst) else 0
            if args.core.endswith(".gz"):
                out = os.path.join(tmp, "mihomo.bin")
                with gzip.open(args.core, "rb") as f, open(out, "wb") as d:
                    shutil.copyfileobj(f, d)
                src_bin = out
            else:
                src_bin = args.core
            shutil.copyfile(src_bin, dst)
            os.chmod(dst, 0o755)
            log(f"bin/mihomo: {old} -> {os.path.getsize(dst)} bytes, mode 755")
        else:
            log("未指定 --core，保留包内原有内核")

        print("[4/5] 插件身份")
        if args.drop_in:
            meta = json.load(open(os.path.join(root, "plugin.json"), encoding="utf-8"))
            final_name = meta.get("name", orig_top)
            log(f'--drop-in：保持上游身份 "{final_name}"，插件目录 {orig_top}/ 不变')
            root_renamed = False
        else:
            rename_plugin(root, args.rename, args.author)
            final_name = args.rename
            # 重命名顶层目录（Decky 用 ZIP 根目录名作为插件目录名）
            final_root = os.path.join(tmp, final_name)
            if final_root != root:
                os.rename(root, final_root)
                root = final_root
                log(f"插件目录: {orig_top}/ -> {final_name}/")

        print("[5/5] 打包")
        count = 0
        with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames.sort()
                for fn in sorted(filenames):
                    full = os.path.join(dirpath, fn)
                    arc = os.path.relpath(full, tmp)
                    rel = os.path.relpath(full, root)
                    # 优先沿用源包里的权限位；bin/ 下的可执行文件强制 755
                    mode = modes.get(rel)
                    if mode is None or (rel.startswith("bin/") and not mode & 0o111):
                        mode = 0o755 if rel.startswith("bin/") else 0o644
                    zi = zipfile.ZipInfo(arc)
                    zi.external_attr = (mode & 0xFFFF) << 16
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    with open(full, "rb") as f:
                        zf.writestr(zi, f.read())
                    count += 1

        print()
        print(f"完成: {args.out}")
        print(f"  插件名: {final_name}")
        print(f"  体积:   {os.path.getsize(args.out)} bytes")
        print(f"  文件数: {count}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
