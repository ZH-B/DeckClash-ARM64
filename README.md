# decky-clash-arm64

[DeckyClash](https://github.com/chenx-dust/DeckyClash)（Clash/Mihomo 的 Decky 插件）的
**非官方 ARM64 打包版**，面向 [Armada OS](https://armadaos.dev/) 等 ARM64 掌机系统。

> 上游是 BSD-3-Clause，本仓库只做重新打包，改动了 2 个文件，其余与上游逐字节一致。
> 详见 [UPSTREAM-NOTICE.md](UPSTREAM-NOTICE.md)。

**当前版本：`v1.3.4-arm64`（基于上游 DeckyClash v1.3.4 + mihomo v1.19.31 arm64）**

```
DeckyClash-ARM64-v1.3.4.zip
SHA256  cd8b61e076031a607537754921789721fbf70d152d42a053710af4cc3a44cf63
```

---

## 为什么需要这个包

在 ARM64 机器上安装**官方** DeckyClash 后，导入任何订阅都会失败：

```
服务器错误  响应状态：500  错误信息：Invalid config
```

根因在上游代码里 —— 内核下载地址写死了 x86-64（`upgrade.py:166,168`、`install.sh:213`）：

```python
f".../MetaCubeX/mihomo/releases/download/{ver}/mihomo-linux-amd64-{ver}.gz"
```

于是 ARM64 机器上装到的是一个 x86-64 内核，它靠 `binfmt_misc` + `qemu-x86_64`
模拟执行。Go 运行时的 CPU 特征探测（`klauspost/cpuid`）和包初始化
（`gopacket/layers.init`）在 QEMU 下会 `SIGSEGV`：

```
unexpected fault address 0x151cd80
fatal error: fault
[signal SIGSEGV: segmentation violation code=0x2 ...]
github.com/klauspost/cpuid/v2.addInfo
github.com/metacubex/gopacket/layers.init
```

而插件导入订阅时会用这个内核去校验配置：

```python
# py_modules/core.py
return_code = subprocess.call([mihomo, "-f", cfg, "-d", dir, "-t"])
return return_code == 0          # ← 子进程被信号打死，返回 -11

# py_modules/subscription.py
valid = core.CoreController.check_config(path)
if not valid:
    return False, "Invalid config"
```

**所以订阅内容从头到尾没被读过。这是架构问题，不是订阅问题**，也跟 anytls /
Hysteria2 之类的新协议无关（那些确实需要新内核，但本项目附带的就是最新内核）。

本包做两处修改：

| 文件 | 改动 |
| --- | --- |
| `py_modules/upgrade.py` | `mihomo-linux-amd64-` → `mihomo-linux-{CORE_ARCH}-`，运行时 `platform.machine()` 探测 |
| `bin/mihomo` | 换成 `mihomo-linux-arm64-v1.19.31`（官方原始二进制，未修改） |

架构探测覆盖 `x86_64 / aarch64 / armv7l / armv6l / i686 / riscv64 / ppc64le /
s390x / loongarch64`。**未知架构沿用 `uname -m` 原值** —— 宁可 404 报错，
也不会静默装上架构不符的二进制。因此这个包在 x86-64 上同样能用。

---

## 支持平台

| 平台 | 状态 |
| --- | --- |
| Armada OS（ARM64，Fedora bootc，内置 Decky Loader） | ✅ 主要目标 |
| 其它带 Decky Loader 的 ARM64 Linux | ✅ 只要 Decky 跑得起来 |
| SteamOS / x86-64（普通 Steam Deck） | ✅ 可用，但没必要，直接用[官方包](https://github.com/chenx-dust/DeckyClash/releases) |

Armada OS 的插件机制**就是 Decky Loader** —— 它的镜像里已经预置了
`decky/armada-control`、`decky/armada-store` 到 `/usr/share/decky-plugins` 并启用了
`plugin_loader.service`，不需要自己装 Decky。

> ⚠️ Armada Store 是只读镜像，只认内置的 `catalog.json`，**无法添加第三方插件源**。
> 所以本插件只能走 Decky 的 **ZIP / URL 安装**（和 `decky-lsfg-vk-arm64` 一样）。

---

## 安装

### 方式 A：Decky 从 ZIP 安装（推荐）

1. 把 `DeckyClash-ARM64-v1.3.4.zip` 放到设备上 Decky 文件选择器够得到的地方，
   例如 `~/Downloads`（**不要下 GitHub 的 Source code，那不是可安装的包**）。
2. 游戏模式 → 按 `...` → **Decky** 图标 → 齿轮 → **设置 → 通用** → 打开
   **开发者模式（Developer Mode）**。
3. 切到 **开发者（Developer）** 页 → **从 ZIP 安装插件** → 选中该 ZIP；
   或在 URL 输入框粘贴 GitHub Release 的 ZIP 直链。
4. 安装完成后插件名为 **Decky Clash ARM64**，目录为
   `~/homebrew/plugins/Decky Clash ARM64`。

### 方式 B：命令行安装

```sh
cd ~/Downloads
unzip -o DeckyClash-ARM64-v1.3.4.zip -d /tmp/dc
sudo rm -rf ~/homebrew/plugins/"Decky Clash ARM64"
sudo mv /tmp/dc/"Decky Clash ARM64" ~/homebrew/plugins/
sudo systemctl restart plugin_loader.service
```

权限位不用手动调 —— 插件启动时 `upgrade.initialize_plugin()` 里有
`recursive_chmod(bin, 0o755)`，而且包内的 `data/` 会自动搬到
`~/homebrew/data/DeckyClash`（GeoIP/GeoSite/dashboard 一并装好）。

### 方式 C：只想让**现有**的官方安装跑起来（不重装）

用本仓库的 [`scripts/fix-installed-plugin.sh`](scripts/fix-installed-plugin.sh)
（自动探测架构 → 下载对应内核 → **连验 3 次再覆盖** → 顺带修补 `upgrade.py`），
或手动操作：

```sh
V=$(curl -fsSL https://github.com/MetaCubeX/mihomo/releases/latest/download/version.txt)
curl -fL --retry 3 -o /tmp/m.gz "https://github.com/MetaCubeX/mihomo/releases/download/$V/mihomo-linux-arm64-$V.gz"
gzip -t /tmp/m.gz && gunzip -f /tmp/m.gz && chmod 755 /tmp/m
cp -a ~/homebrew/plugins/DeckyClash/bin/mihomo ~/mihomo.broken
mv /tmp/m ~/homebrew/plugins/DeckyClash/bin/mihomo
sed -i 's/mihomo-linux-amd64-/mihomo-linux-arm64-/g' ~/homebrew/plugins/DeckyClash/py_modules/upgrade.py
sudo systemctl restart plugin_loader.service
```

---

## 首次使用

1. 打开 **Decky Clash ARM64**，进订阅页，粘贴你的订阅链接导入。
2. 打开代理开关，选节点。
3. 需要在订阅页开启 **TUN** 或按需开启外部控制面板。

### 关于订阅与 User-Agent

部分机场按 `User-Agent` 决定下发什么格式。DeckyClash 的默认 UA 里已经带了
`mihomo / clash.meta / clash-verge / FlClash` 等标识，一般无需改动。

如果确实需要覆盖，编辑（**留空即使用默认 UA，别填垃圾值**）：

```json
// ~/homebrew/settings/DeckyClash/config.json
{ "user_agent_override": "" }
```

> ⚠️ **不要**把 `user_agent_override` 填成 `Clash/...` 或 `ClashForAndroid/...`。
> 很多面板看到这类"不支持新协议"的客户端标识，会返回一个 `proxies:` 为空、
> 但 `proxy-groups` 仍在引用节点的配置，内核直接报 YAML 解析错误，
> 又是一句 `Invalid config`。

### 从官方插件迁移设置

本包默认使用独立的插件身份 `Decky Clash ARM64`，因此设置目录与官方版是分开的。
如果你的订阅/配置在官方版里，迁移一次即可：

```sh
# 官方版的设置目录（两者可能是其一）
ls -d ~/homebrew/settings/DeckyClash ~/homebrew/settings/"Decky Clash" 2>/dev/null

# 复制到新身份下
mkdir -p ~/homebrew/settings/"Decky Clash ARM64"
cp -a ~/homebrew/settings/DeckyClash/. ~/homebrew/settings/"Decky Clash ARM64"/ 2>/dev/null

sudo systemctl restart plugin_loader.service
```

如果你希望**同名覆盖**（设置、订阅直接延续），用 `--drop-in` 重新构建，
或用上面的**方式 C**。

> ⚠️ 两个版本不要同时启用 —— 它们会抢同一组端口（默认 9090 / 50581）。

---

## 自己构建

仓库里只有构建脚本，发布包在 Release 里。这样上游更新时只要重跑一次构建。

```sh
# 1) 拉上游发布包
curl -LO https://github.com/chenx-dust/DeckyClash/releases/latest/download/DeckyClash-full.zip

# 2) 拉对应架构的官方内核
V=$(curl -fsSL https://github.com/MetaCubeX/mihomo/releases/latest/download/version.txt)
curl -LO "https://github.com/MetaCubeX/mihomo/releases/download/$V/mihomo-linux-arm64-$V.gz"

# 3) 出包
python3 scripts/build.py \
    --src  DeckyClash-full.zip \
    --core "mihomo-linux-arm64-$V.gz" \
    --out  DeckyClash-ARM64.zip \
    --rename "Decky Clash ARM64" \
    --author "decky-clash-arm64 (upstream: Chenx Dust)"
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--src` | 上游 `DeckyClash-full.zip`；也可直接传已处理过的包 |
| `--core` | 目标架构的 mihomo（`.gz` 或裸二进制）；省略则保留包内原有内核 |
| `--rename` | 新的插件显示名，默认 `Decky Clash ARM64` |
| `--author` | `plugin.json` 的 author 字段 |
| `--drop-in` | 保持上游身份（同名覆盖，设置与订阅延续） |

脚本做的事：① 修 `upgrade.py` 的架构写死 ② 同样处理 `install.sh`（若有）
③ 替换 `bin/mihomo`（**先验证再打包**）④ 可选重命名 ⑤ 打包并保留权限位。

> ⚠️ **重命名插件时的坑**：上游把插件名硬编码进了前端产物 ——
> `src/index.tsx` 里 `definePlugin(() => ({ name: "Decky Clash", title: ... }))`
> 会被编译进 `dist/index.js`。**`definePlugin` 的 `name` 必须和 `plugin.json` 的
> `name` 一致**，否则 Decky 前端按旧名字去路由 RPC，找不到后端，
> 表现为"插件面板打得开、但数据全是空的、订阅列表为空"。
>
> `build.py --rename` 会把 `dist/index.js` 里所有 `"Decky Clash"` 字符串
> 全量替换掉（而不仅是标题），并在打包时校验零残留。**不要只改 `plugin.json`。**
> 用 `--drop-in` 则完全不需要这套处理。

CI（[.github/workflows/release.yml](.github/workflows/release.yml)）会在打 tag 时
自动完成上述流程并发布 Release —— 出两个包（独立身份版 + 同名覆盖版），
发布前还会做冒烟校验。**想把本仓库发布到自己 GitHub 上分享，见
[PUBLISH.md](PUBLISH.md)。**

---

## 排查

```sh
# 插件日志
journalctl -u plugin_loader -f
tail -50 "$(ls -t ~/homebrew/logs/DeckyClash/* | head -1)"

# 内核是否可用（应打印 linux arm64 并 rc=0）
~/homebrew/plugins/"Decky Clash ARM64"/bin/mihomo -v

# 确认没有在用模拟跑 x86-64 二进制
uname -m
ls /proc/sys/fs/binfmt_misc/ | grep qemu-x86_64
```

| 现象 | 原因 / 处理 |
| --- | --- |
| 面板打得开，但数据全空、**订阅列表为空** | 前端 `definePlugin` 的 `name` 和 `plugin.json` 的 `name` 不一致 → RPC 找不到后端。换用本仓库的构建包（已处理），或用 `--drop-in` |
| 装的时候提示找不到 `plugin.json` | 装成了 GitHub 的 Source code 压缩包，改用 Release 里的 ZIP |
| 导入仍报 `Invalid config` | 先跑上面那条 `mihomo -v`；若不是 `rc=0`，内核没换成功 |
| `mihomo -v` 打印 `linux amd64` | 装的是官方包，不是本包 |
| `mihomo -v` 段错误 | 二进制损坏。**别用插件自带的"升级内核"按钮**，它会先删旧内核再解压新的、全程不校验 |
| 面板打不开 | 检查端口占用与 `external_port` 设置 |
| 找不到"开发者"页 | 回 **设置 → 通用** 先打开开发者模式 |

---

## 许可

BSD 3-Clause，见 [LICENSE](LICENSE)。上游版权归 **Chenx Dust** 所有
（并继承 **Steam Deck Homebrew** 的原始版权）；mihomo 内核版权归 MetaCubeX 所有。
本仓库只做重新打包，未修改内核二进制。

**这是非官方项目。** 相关 issue 请提到本仓库；如果确认是上游问题，
也欢迎同时反馈给 [上游](https://github.com/chenx-dust/DeckyClash/issues) ——
这个架构问题大约 10 行代码就能修好，修好之后本仓库就不需要了。
