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
./start.sh --model 2b    # 默认2B，全语言权重、视觉和缓存放GPU
./start.sh --model 9b    # 先stop.sh再切回保留的9B；默认8层GPU
./start.sh --paused      # 全部就绪后保持自动操作暂停
./start.sh --no-open     # 后台服务就绪，但不自动打开浏览器
./start.sh --timeout 900 # 每个启动阶段最多等待900秒
python3 scripts/lifecycle.py status
./stop.sh --force        # 故障恢复：最终允许强杀卡住的服务器，可能丢失未保存进度
```

启动前无须激活虚拟环境；停止脚本只依赖系统Python。保持桌面会话登录，以保留隐藏客户端的图形上下文。环境路径可通过`HMCL_GAME_ROOT`、`MINECRAFT_JAVA_BIN`、`LLAMA_SERVER_BIN`等现有环境变量配置。详细服务输出在`logs/server.log`、`client.log`、`model.log`、`monitor.log`，启停进度在`logs/lifecycle.log`；最近验收结果在私有`runtime/last-start.json`与`runtime/last-stop.json`。

## 组成

- 默认模型：官方GameScaling-2B-S1在本机转换的Q4_K_M，配套同检查点FP16视觉编码器，语言权重全部GPU。保留9B第三方Q4_K_M兼容副本，可用`--model 9b`切换。
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
uv pip install --python .venv/bin/python -r requirements-conversion.txt
.venv/bin/python scripts/prepare_instances.py
bash scripts/download_models.sh 2b
.venv/bin/python scripts/prepare_2b.py
.venv/bin/python scripts/extract_gtnh_context.py
.venv/bin/python scripts/build_bridge.py
./start.sh
```

默认 llama.cpp 路径为 `/home/rhys/llama.cpp/build/bin/llama-server`，可以通过 `LLAMA_SERVER_BIN` 覆盖。用支持 Qwen3.5 多模态的构建；记录的本机版本为 build 10394 / commit 680a9ae63。

```bash
# 将模型切回纯 CPU；客户端仍使用显卡渲染。
.venv/bin/python scripts/manage.py restart model --profile cpu

# 9B方案只卸载8层；2B默认全部语言权重与视觉GPU。
./stop.sh
MODEL_GPU_LAYERS=8 MODEL_VISION_GPU=1 ./start.sh --model 9b

# 只停止本实验进程；服务器通过 stop 指令正常保存。
.venv/bin/python scripts/manage.py stop all
```

在本机终端运行生命周期脚本；受限容器中的进程列表不一定能看到桌面上的进程。

2B源权重固定版本`8036a8f05659f3ce79c4b98f0ccbee4142a0b53d`，已用hf校验，转换时使用本机llama.cpp的`--no-nextn`排除没有对应权重的MTP声明，再分别导出语言/视觉GGUF与Q4_K_M。`models-2b-manifest.json`和`models-2b-checksums.json`记录转换命令、工具版本和校验值；额外依赖仅用于转换，日常运行不需要PyTorch。

默认2B方案请求全部层卸载，显式将全部语言张量放在CUDA0，视觉编码器、KV缓存及循环状态也使用GPU；进程仍需要系统内存用于程序、文件映射和输入输出。已关闭默认8GiB的旧提示主存缓存，并将上下文检查点限制为2份，避免长时间运行时旧快照挤占游戏内存。2B量化文件约1.56GB、视觉文件约0.67GB。当前实测与GTNH同时运行时，三组相同截图/历史回放显存峰值3943MiB，模型推理中位1.274秒；此前9B/8层GPU记录中位17.736秒。这是两种本机配置的小样本速度比较，不能作为模型能力评测。

如需从头准备保留的9B文件，运行`bash scripts/download_models.sh 9b`和`.venv/bin/python scripts/normalize_gguf.py`，然后停止服务并`./start.sh --model 9b`。未指定模型时使用上次选择，首次默认为2B。

客户端默认隐藏窗口，保持独立的游戏内虚拟焦点和输入；真实键鼠不会进入该测试角色。查看画面和暂停/恢复自动操作均使用 8790 观察台。隐藏窗口仍依赖当前桌面会话和 GPU 上下文，不是完全脱离图形会话的服务。

观察台游戏画面下方提供“服务器命令窗口”，直接执行 Minecraft 命令并显示真实服务器回显，支持带或不带开头 `/`。例如 `gamerule keepInventory`、`tp GameScalingBot 0 100 0`；快捷按钮可设为白天、晴天、和平、死亡不掉落或查询在线玩家。默认勾选“执行时暂停自动操作”，执行后在顶部恢复；命令会使之前正在推理的动作失效，下一轮重新观察当前画面。命令记录保存在私有 `logs/server-commands.jsonl`。

`server-settings.json` 保存可复现的启动默认：和平难度、非极限模式、死亡不掉落。生命周期脚本在启动前配置服务器属性，观察服务在服务器就绪后应用游戏规则并保存世界。命令通道为本机 `127.0.0.1:25575` RCON；随机凭证仅保存在私有测试副本的 `server.properties`，不会发送给观察台页面或进入源码包。

`scripts/build_bridge.py` 同时编译输入隔离 agent。该 agent 针对当前整合包的 lwjgl3ify 2.1.16；输入方法不匹配时终止专用测试客户端，避免悄悄退回真实输入。`scripts/verify_input.py` 可对运行中的测试副本执行回调隔离、虚拟移动和背包交互验收，会暂停自动操作，完成后通过观察台恢复。

## 提示词和续玩记忆

观察台右侧的“提示词与续玩记忆”可以编辑当前目标、固定提示词和个人笔记，保存后下一轮生效，重启自动读回。三项合计最多2000字。你的笔记与程序观测、模型建议分开呈现；编辑时不会被后台刷新覆盖，其他窗口已修改时会提示重新读取。

程序约每两秒保存最近坐标、生命、玩家身份、背包槽位、近期到访区块和物品数量变化；背包不包含箱子等外部容器。停止脚本在退出观察台前再保存一次。角色物品与世界进度仍由Minecraft服务端存档保存，笔记提供给模型续读，不会用笔记覆盖真实背包。

默认每50轮调用同一个本地模型整理一次，也可点击“立即整理续玩笔记”，间隔可设为10–500轮。这次请求只允许模型选择下一步建议和待确认事项，程序生成可读Markdown文档；不会把总结当作游戏动作，也不让模型随意改写已确认事实。任务完成情况目前没有接入验证，一律标为未确认。这个2B动作模型的整理能力有限，此功能还不等同于通用文本模型自由写作。

私有文件在`memory/`：`agent_prompt.md`为固定提示词，`user_notes.md`为个人笔记，`current.md`为自动生成的续玩文档，`state.json`为结构化状态，`history/`保存编辑前、总结后和停止时的文档快照，`summaries/`保存模型整理原文。请通过观察台或编辑前两个文件修改内容；`current.md`会自动重建。固定提示词的公开初始模板在`config/agent-prompt.default.md`。

每次游戏推理会带入精简的续玩上下文，实际注入文本及哈希保存在该轮私有`runtime/episodes/*.json`的`agent_memory`字段。模型权重没有改变，短期画面历史在重启后重新建立。旧观测都带时间，恢复后以新画面/状态为准。记录针对当前同一测试世界，换世界时应先备份并移开`memory/`，再建立对应记录。

`memory/`不进入Git或源码发布包，`scripts/backup.py --full`包含它。只备份或迁移记忆时复制整个`memory/`；继续原角色还需要对应服务器世界存档。

网页预览单独采集和刷新，目标20FPS，可在`game-settings.json`的`client.preview_fps`调整（1–30，重启客户端生效）。它与游戏60FPS、模型每轮推理耗时是三个不同指标。此前截图每秒1张、页面每1.5秒更新一次，网页实际不足1FPS；现在画面不再等待状态轮询或模型推理，使用帧时间去重、顺序加载和浏览器解码后换图，显示实际游戏/采集/网页帧率及最近画面年龄。目标值不保证实际达到，观察台以实测为准。

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
| `model-settings.json` | 2B/9B路径与GPU默认配置 |
| `models-2b-manifest.json` | 官方2B来源与本机转换记录 |
| `vendor/GameScaling/` | Apache-2.0 官方推理工具快照 |
| `instances/` | 私有测试副本，不提交 Git |
| `runtime/episodes/` | 实际推理输入、输出和动作记录，不提交 Git |

GTNH 测试服务器绑定 `127.0.0.1:25565`，模型绑定 `127.0.0.1:8789`，观察台绑定 `127.0.0.1:8790`。模型使用本地推理，不发送游戏画面到外部 API。原桌面服务器与原 HMCL 客户端不作覆盖写入。

服务器已恢复原桌面启动脚本的6GiB初始/最大堆和8区块视距；客户端初始堆2GiB、最大8GiB、8区块视距、60FPS上限与精细画质。此前闭环测试曾使用服务器4GiB、客户端6GiB、两端4区块和30FPS，现已撤回这些保守限制。资源配置在`game-settings.json`，服务器视距在`server-settings.json`；修改后重启对应游戏进程生效。客户端仍渲染854×480，使用独立按键设置；和平和死亡不掉落按用户要求保留。

## 如何理解模型表现

S1 学习的是 Minecraft 轨迹，不保证理解 GTNH 的任务书、科技树或修改配方。本项目通过明确的 GTNH 规则提示和 GUI 操作适配接入；没有对 GTNH 重新训练，也没有保证自主完成科技流程。

`scripts/extract_gtnh_context.py` 从本机整合包的 BetterQuesting 配置提取前两项任务的物品数量与消耗规则，并保留源文件哈希。推理提示会使用该结构化上下文；完整任务书原文不进入源码发布包。第一次在其他机器准备实例后，先运行这个提取脚本。

动作使用200ms包、6个按键子步骤；游戏逻辑仍以Minecraft tick工作，不能宣称每个子步骤都形成独立的服务器动作。移动、使用和GUI按键在包结束后释放。如果6步均包含LB、起止瞄准同一方块、没有混合右键/中键，左键可在该方块上额外保持最多10秒。目标/槽位变化、GUI打开、断连、新动作、暂停或控制变更会结束或更新长按。独立观察服务每250ms发布控制心跳，1500ms未更新则客户端释放；异常同样释放，解析失败不执行。

`scripts/verify_mining.py`暂停AI，在预先确认全为空气的位置搭建临时平台，通过真实生存模式挖掘核验连续性、方块破坏和掉落入包，并测试暂停、心跳中断、目标变化和上限释放；完成后恢复位置并清理平台，保留实际取得的泥土。这是执行器验收，不计作模型自主完成任务。运行证据在私有`runtime/mining-validation.json`。

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
