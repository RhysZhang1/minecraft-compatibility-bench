# 配置模板与本地实例

[English](CONFIGURATION.en.md)

`instance-settings.json` 是标准 JSON 模板；JSON 不支持注释，因此 `_comment` 数组提供说明。`selected: null`、`instances: {}` 表示全新克隆没有运行实例；`templates` 提供四个已测试版本的起点。模板不会自动启用。

| 占位符 | 填入内容 |
|---|---|
| `${JAVA_BIN}` | 该版本可用的 Java 可执行文件 |
| `${CLIENT_DIRECTORY}` | 匹配客户端的目录 |
| `${LIBRARIES_ROOT}` | 包含 libraries 和 assets 的目录 |
| `${SERVER_DIRECTORY}` | 托管副本或外部服务器目录 |

优先运行 `./setup.sh` 选项 6 安装原版，或 `./setup.sh --server-dir /srv/minecraft` 接入现有服务器。向导只把解析后的配置写入 Git 忽略的 `local-instances.json`，不会改写公共模板。

手工配置时使用 `{"instances":{"my-world":{...已填完的模板...}}}`，并运行 `python3 scripts/instances.py select my-world`。需要先完成运行环境和资源准备。所有占位符必须填完；未填写会列出缺失项并提示运行 setup.sh。相对路径按工作区解析；可用 `MCBENCH_WORKSPACE` 或安装后的 `mcbench --workspace /path/to/checkout` 指定工作区。

选择优先级为 `MC_INSTANCE` → `runtime/selected-instance.json` → 公共 selected（默认空）。本地同名实例覆盖公共实例。Java 的环境变量覆盖实例路径；通用 Java 默认从 PATH 查找。llama.cpp 默认在项目 engines/llama.cpp，机器自定义值在 local-settings.json。

新世界应有独立实例 ID、world_id 和记忆目录。已有世界升级时保留角色名、world_id 和服务器目录。此次升级前的内置实例已在本机转存为私有配置，未更换世界和玩家身份。旧 agent_prompt.md 会在缺少 prompt.md 时复制迁移，旧文件保留。

只接入服务器使用 server.managed=false；此模式不要求 server.jar 字段，不管理原服，不应用测试规则。复制模式必须先停止源服务器。
