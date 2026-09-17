# 发布指南（把 decky-clash-arm64 发到 GitHub）

这个仓库**不包含** 55 MB 的插件包，只放构建脚本 —— 插件包由 GitHub Actions 在打 tag 时
自动构建并发布到 Release。所以你只需要把这几 KB 的源码推上去。

---

## 0. 准备

- 一个 GitHub 账号
- 本地有 `git`
- 推送方式二选一：
  - **HTTPS + Personal Access Token**：GitHub → Settings → Developer settings →
    Personal access tokens → 生成一个有 `repo` 权限的 token，推送时当密码用
  - **SSH key**：把公钥加到 GitHub → Settings → SSH keys

> Armada 设备自带 `git`，你也可以**直接在设备上完成整个发布流程**，不用电脑。

---

## 1. 建仓库

在 GitHub 上新建一个**空**仓库（不要勾选 README / .gitignore / License）：

- 名字建议：`decky-clash-arm64`
- 可见性：**Public**（否则别人下 Release 需要登录）
- 描述可以写：
  `Unofficial ARM64 repackaging of DeckyClash for Armada OS and other ARM64 handhelds`

---

## 2. 推送源码

### 方式 A：从打包好的源码包（推荐）

把 `decky-clash-arm64-src.tar.gz` 解压（里面已含 `.git` 和一个 `v1.3.4-arm64.1` tag）：

```sh
tar -xzf decky-clash-arm64-src.tar.gz
cd decky-clash-arm64

# 换成你自己的身份（可选）
git config user.name  "你的名字"
git config user.email "你的邮箱"

git remote add origin https://github.com/<你的账号>/decky-clash-arm64.git
git branch -M main
git push -u origin main
git push origin --tags          # 把 tag 一起推上去，会触发 CI 出包
```

### 方式 B：想让提交记录完全是你的

删掉现成的 `.git` 重新开始：

```sh
cd decky-clash-arm64
rm -rf .git
git init -b main
git config user.name  "你的名字"
git config user.email "你的邮箱"
git add -A
git commit -m "decky-clash-arm64: ARM64 repackaging of DeckyClash v1.3.4"
git remote add origin https://github.com/<你的账号>/decky-clash-arm64.git
git push -u origin main
git tag -a v1.3.4-arm64.1 -m "v1.3.4-arm64.1"
git push origin v1.3.4-arm64.1
```

### 方式 C：直接在 Armada 设备上

把 `decky-clash-arm64-src.tar.gz` 传到设备（`~/Downloads`），然后：

```sh
cd ~/Downloads && tar -xzf decky-clash-arm64-src.tar.gz && cd decky-clash-arm64
git remote add origin https://github.com/<你的账号>/decky-clash-arm64.git
git branch -M main && git push -u origin main && git push origin --tags
```

---

## 3. tag 命名规则（重要）

CI 从 tag 里解析上游版本号去拉对应的官方包：

```
v1.3.4-arm64.1
│      │
│      └─ 你自己的修订号，随便加
└─ 上游 DeckyClash 的版本 tag
```

- 想同步上游新版本：把源码里的版本相关的东西不用改，直接
  `git tag v1.3.5-arm64.1 && git push origin v1.3.5-arm64.1`，
  CI 会去拉 `DeckyClash-full.zip` 的 `v1.3.5` 并配最新 arm64 内核。
- 只改了脚本、上游版本不变：递增修订号，`v1.3.4-arm64.2`。

---

## 4. CI 会做什么

`.github/workflows/release.yml` 在 tag 推送后：

1. 从 tag 解析上游版本，下载 `DeckyClash-full.zip`
2. 下载最新的 `mihomo-linux-<arch>-<ver>.gz`
3. 跑 `scripts/build.py` 出**两个包**：
   - `DeckyClash-arm64-v1.3.4.zip` —— 插件名 `Decky Clash ARM64`（推荐）
   - `DeckyClash-arm64-v1.3.4-dropin.zip` —— 同名覆盖版，给已装官方版的人升级用
4. **冒烟校验**（不过就不发）：`bin/mihomo` 有可执行位、`upgrade.py` 有 `CORE_ARCH`
   补丁且没残留 `mihomo-linux-amd64-`、ZIP 根目录唯一、前端里的插件名和
   `plugin.json` 一致（这一条就是"面板能打开但订阅列表为空"那个坑）
5. 生成 `SHA256SUMS.txt`，发 Release

也可以在 Actions 页面手动触发（`workflow_dispatch`），填上游版本和架构。

---

## 5. 分享给玩家

把 Release 链接发出去即可：

```
https://github.com/<你的账号>/decky-clash-arm64/releases/latest
```

玩家侧的操作（README 里有完整版，一句话版）：

> Decky → 设置 → 通用 → 打开**开发者模式** → **开发者** → **从 ZIP 安装插件**
> → 选 Release 里的 ZIP（**不是 Source code**）

装完自检：

```sh
~/homebrew/plugins/"Decky Clash ARM64"/bin/mihomo -v
# 必须打印 Mihomo Meta ... linux arm64，且退出码 0
```

> Armada Store 是只读镜像，加不了第三方插件源，所以只能走 Decky 的 ZIP / URL 安装
> —— 这一点和 `decky-lsfg-vk-arm64` 一样。

---

## 6. 不想等 CI？

会话文件里已经有两个**构建并验证过**的包，可以直接手动传到 Release：

```
DeckyClash-ARM64-v1.3.4.zip         sha256 cd8b61e0…  （注意：这是修复前的旧包，见下）
DeckyClash-ARM64-dropin-v1.3.4.zip  sha256 b6d5df4e…
```

> ⚠️ 用当前源码重新构建后的独立版是 `2bd4f63f…293a`（修好了前端插件名不一致的问题）。
> **别用旧的那个 `cd8b61e0…`**，那个版本面板会拉不到数据。建议直接用 CI 出的包。

手动发布：Release 页面 → Draft a new release → 选 tag → 把 ZIP 拖进去 → Publish。

---

## 7. 注意事项

- **仓库里不要提交插件 ZIP**（55 MB × 2，git 会很难受）。它们只该出现在 Release。
  `.gitignore` 已经挡掉了。
- **不要提交任何个人数据**：构建脚本只从上游官方包 + mihomo 官方发布取文件，
  产物里不含订阅链接、控制器密钥、内网 IP。发布前可以自查一遍：

  ```sh
  python3 - <<'PY'
  import zipfile, re
  z = zipfile.ZipFile('DeckyClash-ARM64-v1.3.4.zip')
  for pat in (rb'你的订阅域名', rb'你的token', rb'192\.168\.\d+\.\d+'):
      hit = [n for n in z.namelist() if not n.endswith('/') and re.search(pat, z.read(n), re.I)]
      print(pat, hit or 'OK')
  PY
  ```

- **建议同时给上游提个 PR**。这个架构问题大概 10 行代码就能修：
  `py_modules/upgrade.py` 加一个 `platform.machine()` 映射、URL 里换成变量。
  修好之后这个仓库就不需要了，对所有人都更好。
  相关 issue：[#20](https://github.com/chenx-dust/DeckyClash/issues/20)、
  [#30](https://github.com/chenx-dust/DeckyClash/issues/30)
- 上游是 **BSD-3-Clause**，fork 发布合法，`LICENSE` 里已完整保留上游版权声明，
  `UPSTREAM-NOTICE.md` 说明了改动范围。发布时请保持这两份文件。
