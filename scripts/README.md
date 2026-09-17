# scripts/

| 脚本 | 用途 |
| --- | --- |
| `build.py` | **构建器**。把上游发布包改造成架构自适应版本并重新打包。CI 用的就是它。 |
| `fix-installed-plugin.sh` | **就地修复**。不重装插件，直接把已安装的插件内核换成当前架构的（先连验 3 次再覆盖），并修补 `upgrade.py`。适合"只想让现有的跑起来"。 |

## 常用示例

```sh
# 出 ARM64 独立版（插件名 Decky Clash ARM64）
python3 scripts/build.py \
  --src DeckyClash-full.zip --core mihomo-linux-arm64-v1.19.31.gz \
  --out DeckyClash-ARM64.zip

# 出同名覆盖版（设置、订阅直接延续）
python3 scripts/build.py \
  --src DeckyClash-full.zip --core mihomo-linux-arm64-v1.19.31.gz \
  --out DeckyClash-ARM64-dropin.zip --drop-in

# 就地修复已安装的插件
bash scripts/fix-installed-plugin.sh --restart
```
