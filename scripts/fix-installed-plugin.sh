#!/usr/bin/env bash
# ============================================================================
#  DeckyClash 架构修复脚本
#
#  背景：DeckyClash 的 install.sh 和 py_modules/upgrade.py 把内核下载地址
#        写死成 mihomo-linux-amd64-*.gz，在 ARM64 / 其它架构的机器上会装错
#        架构的内核。x86-64 二进制在 ARM64 上靠 binfmt_misc + qemu-x86_64
#        模拟执行，Go 运行时的 CPU 探测（klauspost/cpuid）和包初始化
#        （gopacket/layers.init）会在 QEMU 下段错误。
#
#  症状：插件导入任何订阅都报  "Invalid config"
#        （因为 check_config 跑 mihomo -t，子进程被 SIGSEGV 打死）
#
#  用法（在 DeckyClash 所在机器的终端里）：
#     bash deckyclash-arch-fix.sh              # 下载正确架构内核 + 打补丁
#     bash deckyclash-arch-fix.sh --no-patch   # 只换内核，不改插件源码
#     bash deckyclash-arch-fix.sh --restart    # 换完顺手重启 Decky
# ============================================================================

set -u

RED=$'\e[31m'; GRN=$'\e[32m'; YEL=$'\e[33m'; CYA=$'\e[36m'; DIM=$'\e[2m'; RST=$'\e[0m'
ok()   { printf '%s  ✔ %s%s\n' "$GRN" "$*" "$RST"; }
bad()  { printf '%s  ✘ %s%s\n' "$RED" "$*" "$RST"; }
warn() { printf '%s  ! %s%s\n' "$YEL" "$*" "$RST"; }
info() { printf '%s    %s%s\n' "$DIM" "$*" "$RST"; }
hd()   { printf '\n%s== %s ==%s\n' "$CYA" "$*" "$RST"; }
die()  { bad "$*"; exit 1; }

DO_PATCH=1; DO_RESTART=0
for a in "$@"; do
  case "$a" in
    --no-patch) DO_PATCH=0 ;;
    --restart)  DO_RESTART=1 ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *) die "未知参数: $a" ;;
  esac
done

# ----------------------------------------------------------------------------
# 1. 检测架构 -> mihomo 资产后缀
# ----------------------------------------------------------------------------
hd "架构检测"
RAW_ARCH=$(uname -m)
echo "    uname -m = $RAW_ARCH"

case "$RAW_ARCH" in
  x86_64|amd64)        ARCH=amd64 ;;
  aarch64|arm64)       ARCH=arm64 ;;
  armv7l|armv7)        ARCH=armv7 ;;
  armv6l|armv6)        ARCH=armv6 ;;
  i386|i486|i586|i686) ARCH=386   ;;
  riscv64)             ARCH=riscv64 ;;
  ppc64le)             ARCH=ppc64le ;;
  s390x)               ARCH=s390x ;;
  loongarch64)         ARCH=loong64-abi2 ;;
  *)
    warn "没见过的架构 $RAW_ARCH，按原样尝试作为资产后缀"
    ARCH="$RAW_ARCH" ;;
esac
ok "mihomo 资产后缀 = $ARCH"

# 是否在跑模拟：ARM 机器上出现 amd64 的解释器就是被模拟了
if [ "$ARCH" != "amd64" ] && [ -e /proc/sys/fs/binfmt_misc/qemu-x86_64 ]; then
  warn "检测到 qemu-x86_64 的 binfmt 注册 —— 说明本机确实在用模拟跑 amd64 二进制"
  info "这正是段错误的来源，换成原生 $ARCH 内核即可根治"
fi

# ----------------------------------------------------------------------------
# 2. 定位插件
# ----------------------------------------------------------------------------
hd "定位插件"
PLUGIN_DIR=""
for d in "$HOME/homebrew/plugins/DeckyClash" /home/deck/homebrew/plugins/DeckyClash; do
  [ -d "$d" ] && PLUGIN_DIR="$d" && break
done
[ -n "$PLUGIN_DIR" ] || die "找不到 DeckyClash 插件目录"
ok "插件目录: $PLUGIN_DIR"

CORE_PATH="$PLUGIN_DIR/bin/mihomo"
if [ -f "$CORE_PATH" ]; then
  OLD_SUM=$(sha256sum "$CORE_PATH" 2>/dev/null | cut -d' ' -f1)
  info "现有内核 sha256: ${OLD_SUM:0:16}…  ($(stat -c%s "$CORE_PATH") bytes)"
else
  warn "现有内核不存在，将全新安装"
fi

# ----------------------------------------------------------------------------
# 3. 下载正确架构的内核
# ----------------------------------------------------------------------------
hd "下载 mihomo ($ARCH)"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

V=$(curl -fsSL --max-time 30 "https://github.com/MetaCubeX/mihomo/releases/latest/download/version.txt" 2>/dev/null)
[ -n "${V:-}" ] || die "拿不到版本号 —— 本机可能连不上 GitHub，见脚本末尾的手动方案"
ok "最新版本: $V"

URL="https://github.com/MetaCubeX/mihomo/releases/download/$V/mihomo-linux-$ARCH-$V.gz"
info "URL: $URL"

for i in 1 2 3 4 5; do
  curl -fL -C - --retry 2 --retry-delay 2 --max-time 300 -o "$WORK/m.gz" "$URL" && \
    gzip -t "$WORK/m.gz" 2>/dev/null && { ok "下载完成且 gzip 完整 ($(stat -c%s "$WORK/m.gz") bytes)"; break; }
  warn "第 $i 次下载不完整，续传中…"
  [ "$i" = 5 ] && die "下载失败，检查网络或改用文末的手动方案"
done

gunzip -f "$WORK/m.gz" || die "解压失败"
chmod +x "$WORK/m"

# ----------------------------------------------------------------------------
# 4. 先验证再安装（避免像插件自己那样先删后写）
# ----------------------------------------------------------------------------
hd "验证新内核"
VOUT=$("$WORK/m" -v 2>&1 | head -1)
info "$VOUT"
for i in 1 2 3; do
  "$WORK/m" -v >/dev/null 2>&1
  rc=$?
  echo "    第 $i 次运行 rc=$rc"
  [ "$rc" != 0 ] && die "新内核也跑不起来（rc=$rc），别安装；把这行输出发给开发者"
done
ok "三次运行全部 rc=0，可以安装"

# ----------------------------------------------------------------------------
# 5. 安装
# ----------------------------------------------------------------------------
hd "安装内核"
if [ -f "$CORE_PATH" ]; then
  BAK="$CORE_PATH.bak.$(date +%Y%m%d%H%M%S)"
  if cp -a "$CORE_PATH" "$BAK" 2>/dev/null; then ok "已备份到 $BAK"
  else warn "备份失败（权限？），继续尝试安装"; fi
fi

if ! mv "$WORK/m" "$CORE_PATH" 2>/dev/null; then
  warn "无写权限，改用 sudo"
  sudo mv "$WORK/m" "$CORE_PATH" || die "安装失败"
fi
chmod 755 "$CORE_PATH" 2>/dev/null || sudo chmod 755 "$CORE_PATH"
[ -n "${SUDO_USER:-}" ] && sudo chown "$(id -un):$(id -gn)" "$CORE_PATH" 2>/dev/null

FINAL=$( "$CORE_PATH" -v 2>&1 | head -1 )
ok "安装完成: $FINAL"

# ----------------------------------------------------------------------------
# 6. 打补丁：让插件自己的“升级内核”也下载正确架构
# ----------------------------------------------------------------------------
if [ "$DO_PATCH" = 1 ]; then
  hd "修补插件的下载地址（否则下次升级内核又会被换回 amd64）"
  for f in "$PLUGIN_DIR/py_modules/upgrade.py" "$PLUGIN_DIR/install.sh"; do
    [ -f "$f" ] || continue
    if grep -q 'mihomo-linux-amd64-' "$f" 2>/dev/null; then
      cp -a "$f" "$f.bak.archfix" 2>/dev/null || true
      if sed -i "s/mihomo-linux-amd64-/mihomo-linux-$ARCH-/g" "$f" 2>/dev/null; then
        ok "$(basename "$f"): mihomo-linux-amd64- → mihomo-linux-$ARCH-"
      else
        sudo sed -i "s/mihomo-linux-amd64-/mihomo-linux-$ARCH-/g" "$f" \
          && ok "$(basename "$f") 已修补（sudo）" || warn "$(basename "$f") 修补失败"
      fi
    else
      info "$(basename "$f"): 没找到 mihomo-linux-amd64- ，跳过"
    fi
  done
  warn "注意：DeckyClash 插件本身升级后会覆盖 py_modules/，需要重跑本脚本"
fi

# ----------------------------------------------------------------------------
# 7. 收尾
# ----------------------------------------------------------------------------
hd "复原配置文件"
CONFIG_JSON="$HOME/homebrew/settings/DeckyClash/config.json"
[ -f /home/deck/homebrew/settings/DeckyClash/config.json ] && \
  CONFIG_JSON=/home/deck/homebrew/settings/DeckyClash/config.json
if [ -f "$CONFIG_JSON" ]; then
  python3 - "$CONFIG_JSON" <<'PY' 2>/dev/null && ok "已清空 user_agent_override（如果之前设过）"
import json, sys
p = sys.argv[1]
d = json.load(open(p))
if d.get("user_agent_override"):
    print("      原来是:", repr(d["user_agent_override"]))
    d["user_agent_override"] = ""
    json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
PY
fi

if [ "$DO_RESTART" = 1 ]; then
  hd "重启 Decky"
  sudo systemctl restart plugin_loader.service && ok "plugin_loader.service 已重启"
else
  printf '\n%s下一步：sudo systemctl restart plugin_loader.service  （或加 --restart 参数重跑）%s\n' "$DIM" "$RST"
fi

cat <<EOF

${GRN}修复完成。${RST}回 Decky 里重新导入订阅即可。

如果 GitHub 在这台机器上连不上，手动方案：
  1. 在电脑/手机上下载  mihomo-linux-$ARCH-$V.gz
     https://github.com/MetaCubeX/mihomo/releases/download/$V/mihomo-linux-$ARCH-$V.gz
  2. 解压得到 mihomo，拷到  $CORE_PATH
  3. chmod 755 $CORE_PATH && $CORE_PATH -v
EOF
