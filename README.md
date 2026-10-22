# GameScaling × GT New Horizons 本地实验

将论文 GameScaling 的 Minecraft 操作策略接入 GTNH 2.8.4 / Minecraft 1.7.10。

## 日常一键启动与完全停止

在当前项目目录执行：

```bash
./start.sh
./stop.sh
```

两个脚本都可从其他目录用绝对路径调用。启动脚本使用本机现有 HMCL 资源、Java、llama.cpp 和本目录权重；检查并补齐缺失的项目Python环境、独立测试副本及桥接，校验模型文件，启动服务器与模型，等待命令接口和模型就绪，再启动隐藏客户端和观察台。客户端实际连入服务器、输入隔离及默认游戏规则确认后才开启模型自动操作，并打开8790观察台。整个过程无需先打开HMCL或手动启动服务端。

停止脚本暂停自动操作、关闭观察台和客户端，通过控制台执行save-all与stop正常保存世界，退出模型并核对本项目进程和监听端口。通过实际进程参数识别本项目服务，PID文件丢失时仍可找回；重复启动会复用同配置服务，重复停止可直接成功。启动失败会清理本次新启动的服务；启动期间另运行stop.sh会请求取消。正常服务器退出超时会报告错误并保留进程，避免直接中断世界保存。

```bash
./start.sh --profile cpu  # 纯CPU推理；切换配置前先stop.sh
./start.sh --paused      # 全部就绪后保持自动操作暂停
./start.sh --no-open     # 后台服务就绪，但不自动打开浏览器
./start.sh --timeout 900 # 每个启动阶段最多等待900秒
python3 scripts/lifecycle.py status
./stop.sh --force        # 故障恢复：最终允许强杀卡住的服务器，可能丢失未保存进度
```

启动前无须激活虚拟环境；停止脚本只依赖系统Python。保持桌面会话登录，以保留隐藏客户端的图形上下文。环境路径可通过`HMCL_GAME_ROOT`、`MINECRAFT_JAVA_BIN`、`LLAMA_SERVER_BIN`等现有环境变量配置。详细服务输出在`logs/server.log`、`client.log`、`model.log`、`monitor.log`，启停进度在`logs/lifecycle.log`；最近验收结果在私有`runtime/last-start.json`与`runtime/last-stop.json`。

## 组成

- 模型：GameScaling-9B-S1 的第三方 Q4_K_M 转换，配套该检查点的 FP16 视觉投影。
- 推理：llama.cpp，支持纯 CPU 或少量层 GPU 卸载。与原始 BF16 的能力差异未作等价性验证。
- 游戏：HMCL 中现有客户端和桌面服务器的独立副本，使用专用离线角色 GameScalingBot。
- 桥接：客户端 Forge 模组内截取渲染画面、施加短时按键和 GUI 事件。操作不发送到整个桌面。
- 后台输入：专用 Java agent 隔离测试客户端的键鼠入口，保留独立虚拟按键和鼠标。窗口隐藏，不抢焦点或抓取桌面鼠标；GPU 继续渲染，画面在观察台查看。
- 观察台：`http://127.0.0.1:8790`，显示截图、实际模型输出、动作、运行记录、内存和显存。

## 安装与复现

先准备合法取得的 GTNH 2.8.4 客户端、服务端及对应 Java。当前启动器读取本机 HMCL 依赖与资源，路径在 `scripts/launch_game.py` 中。迁移时调整 `SOURCE` 和 `JAVA`，不需要 HMCL 账号文件或登录令牌。

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/prepare_instances.py
bash scripts/download_models.sh
.venv/bin/python scripts/normalize_gguf.py
.venv/bin/python scripts/extract_gtnh_context.py
.venv/bin/python scripts/build_bridge.py
./start.sh
```

默认 llama.cpp 路径为 `/home/rhys/llama.cpp/build/bin/llama-server`，可以通过 `LLAMA_SERVER_BIN` 覆盖。用支持 Qwen3.5 多模态的构建；记录的本机版本为 build 10394 / commit 680a9ae63。

```bash
# 将模型切回纯 CPU；客户端仍使用显卡渲染。
.venv/bin/python scripts/manage.py restart model --profile cpu

# 默认只卸载 8 层，其余在内存。按实测余量调整。
MODEL_GPU_LAYERS=8 MODEL_VISION_GPU=1 .venv/bin/python scripts/manage.py restart model --profile balanced

# 只停止本实验进程；服务器通过 stop 指令正常保存。
.venv/bin/python scripts/manage.py stop all
```

在本机终端运行生命周期脚本；受限容器中的进程列表不一定能看到桌面上的进程。

客户端默认隐藏窗口，保持独立的游戏内虚拟焦点和输入；真实键鼠不会进入该测试角色。查看画面和暂停/恢复自动操作均使用 8790 观察台。隐藏窗口仍依赖当前桌面会话和 GPU 上下文，不是完全脱离图形会话的服务。

观察台游戏画面下方提供“服务器命令窗口”，直接执行 Minecraft 命令并显示真实服务器回显，支持带或不带开头 `/`。例如 `gamerule keepInventory`、`tp GameScalingBot 0 100 0`；快捷按钮可设为白天、晴天、和平、死亡不掉落或查询在线玩家。默认勾选“执行时暂停自动操作”，执行后在顶部恢复；命令会使之前正在推理的动作失效，下一轮重新观察当前画面。命令记录保存在私有 `logs/server-commands.jsonl`。

`server-settings.json` 保存可复现的启动默认：和平难度、非极限模式、死亡不掉落。生命周期脚本在启动前配置服务器属性，观察服务在服务器就绪后应用游戏规则并保存世界。命令通道为本机 `127.0.0.1:25575` RCON；随机凭证仅保存在私有测试副本的 `server.properties`，不会发送给观察台页面或进入源码包。

`scripts/build_bridge.py` 同时编译输入隔离 agent。该 agent 针对当前整合包的 lwjgl3ify 2.1.16；输入方法不匹配时终止专用测试客户端，避免悄悄退回真实输入。`scripts/verify_input.py` 可对运行中的测试副本执行回调隔离、虚拟移动和背包交互验收，会暂停自动操作，完成后通过观察台恢复。

## 文件与适配范围

| 路径 | 内容 |
|---|---|
| `start.sh` / `stop.sh` | 一键冷启动与完全停止 |
| `scripts/lifecycle.py` | 就绪等待、异常清理和完整停止验收 |
| `bridge/src/` | 客户端 Forge 桥接源码 |
| `input/src/` | 隐藏窗口与虚拟输入隔离 agent 源码 |
| `src/monitor.py` | 观察台与截图→模型→动作闭环 |
| `src/server_console.py` | 本机 Minecraft 命令通道与回显 |
| `server-settings.json` | 服务器默认难度与游戏规则 |
| `scripts/` | 下载、编译、启动和备份 |
| `docs/ISSUES.md` | 实际问题与解决记录 |
| `models-manifest.json` | 上游仓库与固定版本 |
| `vendor/GameScaling/` | Apache-2.0 官方推理工具快照 |
| `instances/` | 私有测试副本，不提交 Git |
| `runtime/episodes/` | 实际推理输入、输出和动作记录，不提交 Git |

GTNH 测试服务器绑定 `127.0.0.1:25565`，模型绑定 `127.0.0.1:8789`，观察台绑定 `127.0.0.1:8790`。模型使用本地推理，不发送游戏画面到外部 API。原桌面服务器与原 HMCL 客户端不作覆盖写入。

测试副本将服务端视距设为 4、难度设为和平，以便先验证慢速模型闭环；这不是原难度下的游戏能力评测。客户端渲染 854×480，独立按键设置，启动堆上限 6 GiB；服务器堆上限 4 GiB。

## 如何理解模型表现

S1 学习的是 Minecraft 轨迹，不保证理解 GTNH 的任务书、科技树或修改配方。本项目通过明确的 GTNH 规则提示和 GUI 操作适配接入；没有对 GTNH 重新训练，也没有保证自主完成科技流程。

`scripts/extract_gtnh_context.py` 从本机整合包的 BetterQuesting 配置提取前两项任务的物品数量与消耗规则，并保留源文件哈希。推理提示会使用该结构化上下文；完整任务书原文不进入源码发布包。第一次在其他机器准备实例后，先运行这个提取脚本。

动作使用 200ms 包、6 个按键子步骤。执行器按渲染事件调度，游戏逻辑仍以 Minecraft tick 工作，不能宣称每个子步骤都形成独立的服务器动作。所有按键在包结束后释放，解析失败不执行。

观察台仅展示模型实际生成的推理文字。空推理代表模型直接输出动作，不补写解释。请求采用官方空历史推理块和 ChatML 结构，通过 llama.cpp 原生多模态 completion 接口保留完整生成文本。

## 备份与 GitHub

源码、适配记录及上游版本清单在本地 Git 保存。游戏二进制、世界、权重、账号和本机依赖不进入 GitHub 源码包。完整本地备份另含当前模型和测试副本，不能直接当作公开发布包。

上游 GameScaling 推理代码使用 Apache-2.0，保留在 `vendor/GameScaling/LICENSE`。模型和整合包的权利与使用条款分别属于各上游。当前工程没有配置 Git 远程，也没有进行上传。

```bash
# 生成当前已提交代码的源文件包与完整本地 Git 历史。
.venv/bin/python scripts/backup.py

# 完整私有备份另包含模型、客户端、服务器、世界和运行证据。
# 先正常停止客户端和服务器，避免复制写入中的世界。
.venv/bin/python scripts/manage.py stop client
.venv/bin/python scripts/manage.py stop server
.venv/bin/python scripts/backup.py --full
```
