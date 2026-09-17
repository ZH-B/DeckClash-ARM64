# Upstream notice / 上游说明

本仓库是 [chenx-dust/DeckyClash](https://github.com/chenx-dust/DeckyClash) 的
**非官方 ARM64 重新打包项目**，不是上游的分支开发，也不代表上游立场。

This repository is an **unofficial ARM64 repackaging project** of
[chenx-dust/DeckyClash](https://github.com/chenx-dust/DeckyClash).

## 我们改了什么

**只改了两件事，其余 319 个文件与上游逐字节一致。**

### 1. `py_modules/upgrade.py` —— 修掉写死的 CPU 架构

上游（v1.3.4）在 166 / 168 行把内核下载地址写死：

```python
f"https://github.com/{CORE_REPO}/releases/download/{ver}/mihomo-linux-amd64-{ver}.gz"
```

我们改成运行时探测：

```python
def _detect_core_arch() -> str:
    import platform
    _m = platform.machine().lower()
    return {"x86_64": "amd64", "aarch64": "arm64", ...}.get(_m, _m)

CORE_ARCH = _detect_core_arch()
# ...
f".../mihomo-linux-{CORE_ARCH}-{ver}.gz"
```

同样的改动也应用到 `install.sh:213`（如果包内存在该文件）。

### 2. `bin/mihomo` —— 换成 ARM64 内核

上游发布包内置 `mihomo-linux-amd64`（v1.3.4 附带 v1.19.20）。本包替换为
[MetaCubeX/mihomo](https://github.com/MetaCubeX/mihomo) 官方发布的
`mihomo-linux-arm64-v1.19.31`，未做任何修改，二进制逐字节来自官方 Release。

### 3. 插件身份（可选，构建时可关掉）

为便于与上游插件共存并独立发布，本包默认把显示名从 `Decky Clash` 改为
`Decky Clash ARM64`（`plugin.json` 的 `name` 与 `dist/index.js` 里的面板标题）。
用 `--drop-in` 参数可以保持上游身份。

## 为什么需要这个项目

ARM64 机器上装官方包后，导入任何订阅都会报 **`Invalid config`**：

```
DeckyClash 装的是 x86-64 内核
  └─ ARM64 上靠 binfmt_misc + qemu-x86_64 模拟执行
       └─ Go 运行时的 CPU 特征探测（klauspost/cpuid）与包初始化
          （gopacket/layers.init）在 QEMU 下 SIGSEGV
            └─ mihomo -t 子进程被信号打死，返回 -11
                 └─ core.check_config() 返回 False
                      └─ subscription.download_sub() 返回 "Invalid config"
```

订阅本身完全正常 —— 上游的 `check_config` 用崩溃的内核去校验配置文件，
`subprocess.call()` 拿到非 0 就判定配置非法。换句话说，**这是架构问题，
不是订阅问题，也不是 anytls 等新协议的问题**。

## 上游许可

BSD 3-Clause License，见 [LICENSE](LICENSE)。上游版权归 Chenx Dust 所有
（并继承 Steam Deck Homebrew 的原始版权）。本仓库的打包脚本与原包改造同样以
BSD-3-Clause 发布，完整保留了上游版权声明。

## 上游资源

- 上游仓库：<https://github.com/chenx-dust/DeckyClash>
- 上游发布：<https://github.com/chenx-dust/DeckyClash/releases>
- Mihomo 内核：<https://github.com/MetaCubeX/mihomo/releases>
- 上游 FAQ：<https://github.com/chenx-dust/DeckyClash/blob/main/docs/FAQ.md>

## 建议

这个架构问题很小（约 10 行代码），**强烈建议同时向上游提 issue / PR**，
这样以后就不需要本仓库了。相关 issue 参考：

- [#20 geoip 缺失导致导入订阅失败](https://github.com/chenx-dust/DeckyClash/issues/20)（同类"导入报错"问题）
- [#30 客户端版本太老](https://github.com/chenx-dust/DeckyClash/issues/30)
