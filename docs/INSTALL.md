# 安装、运行与排障

这是一个实验性的 Linux Minecraft 视觉模型控制工具。请先在独立测试世界使用；原版基础操作通过不代表模型能完成复杂合成或任意整合包任务。

## 1. 系统条件

本机验证环境为 Linux x86_64、KWin 6.8、Xwayland、libei 与 NVIDIA RTX 5060（8GB显存），内存约30GiB。未验证 Windows、macOS、其他桌面合成器或 AMD/Intel 显卡。KWin 使用独立虚拟会话，当前桌面不必切换成 KDE，但系统必须具备可运行的 KWin/Xwayland 和 OpenGL 驱动。

由系统提供以下组件：

- Python 3.11（推荐同时有 uv；无 uv 时使用 venv/pip）。
- KWin Wayland、Xwayland、dbus-run-session、libX11、libei、D-Bus、OpenGL驱动。
- 构建工具：C/C++编译器、pkg-config，以及 libei 和 D-Bus 的开发文件；JDK 17或更新版本，包含 javac、jar。
- git、cmake、zstd；CUDA模型引擎构建另需 CUDA工具链。CPU构建不需要CUDA。

项目不自动安装系统软件包，不更改显卡驱动、系统Python或系统Java。不同发行版的软件包名称不同，请按系统软件包管理器安装上述组件；运行 `./setup.sh --doctor` 查看工具、运行库和项目依赖状态。

当前2B量化文本模型约1.56GB，视觉编码器约0.67GB；实际显存还包括KV缓存和游戏渲染。本机2B可以完整卸载到显卡。原始检查点、F16中间文件、Java、游戏资源、日志和完整备份会继续占用磁盘，建议至少预留40GiB；保留完整私有备份时再留足一份空间。

## 2. 获取源码并准备环境

```bash
git clone git@github.com:RhysZhang1/minecraft-gamescaling-agent.git
cd minecraft-gamescaling-agent
./setup.sh --doctor
./setup.sh
```

未配置GitHub SSH的用户可用HTTPS克隆：

```bash
git clone https://github.com/RhysZhang1/minecraft-gamescaling-agent.git
```

向导选项按下面顺序使用：

1. **配置环境与依赖**：创建项目 `.venv/`，安装运行依赖与 `hf` 下载工具。需要从官方2B检查点转换时，同时安装转换依赖。Git克隆还应选择准备ASM SDK。
2. **下载并编译llama.cpp**：使用项目内新目录（例如 `engines/llama.cpp`），选择CUDA或CPU。脚本固定引擎提交，只创建新目录，不覆盖已有源码树。已有兼容引擎可在环境配置中直接指定。
3. **安装指定版本原版客户端、服务器与Java**：建议先选1.20.1。指定独立服务器父目录、未占用的游戏/RCON端口。客户端、共享资源和Java放在项目 `instances/`。向导登记正确的Java，独立服务器入口与完整启动入口使用同一运行时。
4. **检测、下载、准备模型**：选2b，先下载、再本地转换，最后选中。下载固定Hugging Face revision；2B转换前验证官方权重SHA256。转换输出只在成功后发布为最终文件，中断不会留下被当作成品的GGUF。
5. 再运行 `./setup.sh --verify-models`，检查路径和模型哈希。

2B的下载、F16转换、视觉转换和Q4量化都在本机完成。只下载检查点还不能启动。转换需要较多内存与临时空间。9B也是可选项，但8GB显存通常需要部分卸载/CPU运行，本机默认仍使用2B。

安装器逐文件检查官方SHA1，已存在但哈希错误的文件会报错并保留，避免静默覆盖。Java安装不能仅凭bin/java存在就判定完成，重跑会补齐和校验所有文件。服务器下载使用带版本标记的临时目录，失败可重试，成功后才发布最终服务器目录；完整服务器目录已存在时不会覆盖。向导重用登记的服务器前会显示真实路径和端口，新建另一世界应使用新的实例ID导入。

### EULA

服务器需要你自行阅读并接受 [Minecraft EULA](https://aka.ms/MinecraftEULA)。向导可复制一个你已接受条款的 `eula.txt`；留空也可以下载文件，但启动前必须自行完成接受记录。脚本不会替你接受条款，缺少记录时会在启动前明确报出路径。

### Git源码与发行附件

Git源码和GitHub自动生成的Source code压缩包不含预编译桥接文件。首次启动会构建本项目的只读Java采集器和libei输入库，需要前述JDK、ASM SDK与C开发依赖。

若使用本项目自行打包的 `minecraft-agent-source-*.tar.gz`，其中 `release/` 附有本项目编译的桥接文件及SHA256清单，启动时可自动恢复；ABI/发行版不同仍应重新编译原生库。模型、Minecraft客户端、世界和账户数据都不在公开发行文件中。

## 3. 完整启停

```bash
./start.sh --instance vanilla-1-20-1 --paused --no-open
# 打开 http://127.0.0.1:8790/，点击“恢复自动操作”
./stop.sh
```

- `./start.sh`：启动上次实例，默认开启AI和GPU推理，并尝试打开浏览器。
- `--paused`：服务器、客户端、模型和观察台都启动，但AI暂停。
- `--no-open`：不自动打开浏览器；客户端始终在私有虚拟会话内，不显示桌面窗口。
- `--profile cpu`：模型用CPU/内存，游戏继续使用显卡；改变运行模式前先停止。
- `--model 2b|9b`：选择模型；改变已运行模型前先停止。
- `--timeout 600`：每个就绪阶段的等待秒数；整合包可适当增加。
- `python3 scripts/lifecycle.py status`：只查看本项目服务状态。
- `./stop.sh`：暂停并保存记忆，释放输入、退出客户端、保存并关闭本地世界，再停止模型和私有显示；也停止登记的独立测试服。
- `./stop.sh --force`：仅在正常保存退出和JVM关闭均超时后才允许强杀服务器，可能丢失未完成的保存。通常不用。

这些入口可以从任意当前目录通过绝对路径调用，项目路径允许包含空格。重复启动会复用同一套已运行服务，不启动第二套；重复停止也可正常完成。停止不依赖 `.venv` 正常工作，使用系统Python。丢失PID文件时按精确命令及实例目录找回本项目进程，不对其他Java/桌面应用执行通用杀进程。

启动过程中运行stop.sh会请求取消启动并清理已经启动的组件；启动失败也会清理该次新启动的服务。遇到别的进程占用端口会保留它并报错，不结束该进程。切换实例前先停止，或者使用观察台的一键保存切换。

## 4. 观察与保存

观察台仅监听127.0.0.1:8790，模型接口为127.0.0.1:8789。服务器默认仅监听本机，使用固定离线测试角色，不读取HMCL账号。远程访问、正版账户登录与认证服务器不在当前安装流程中。

页面可以看真实画面、实际生成的文本/动作、结果反馈、服务器命令回显和续玩文档。和平与死亡不掉落会在启动时应用并验证；26.3使用对应的新规则名称。

世界和角色物品保存在各自服务端，固定角色名/离线UUID让重启后继续。文档记忆按实例和world_id隔离；模型进程中的上下文本身不会跨进程保留。新世界请创建新实例和记忆目录，避免混用旧世界笔记。

## 5. 常见问题

| 现象 | 检查与处理 |
|---|---|
| 缺少模型/模板/校验记录 | 运行向导的模型下载与准备，或恢复完整私有备份；不要只修改模型路径 |
| 缺少ASM/找不到javac | 安装JDK，向导准备ASM；确认javac可执行 |
| libei编译失败 | 确认C编译器、pkg-config、libei和D-Bus开发文件齐全；看构建错误 |
| Java版本不符 | 向导安装对应官方运行时；检查实例覆盖和MINECRAFT_JAVA_BIN环境变量 |
| 端口占用 | 查看报出的端口，停止自己的冲突应用或为实例配置空闲端口；工具不会代杀其他程序 |
| Java安装中断 | 原命令/向导重跑，逐文件核验；不要因bin/java存在而跳过 |
| 服务器下载中断 | 原安装命令重跑，会使用带版本标记的.installing目录；完整世界不覆盖 |
| 世界启动慢 | 查看logs/server.log；适当增加--timeout，不以端口打开代替客户端就绪 |
| 看不到游戏/输入未隔离 | 检查logs/display.log、bridge.log、client.log；禁止将DISPLAY手动改为桌面会话作为绕过 |
| AI反复无效操作后暂停 | 通用反馈在有限次重观察后保留现场暂停；查看当前画面、目标和历史结果再恢复 |
| 网页比游戏帧率低 | 游戏上限60，采集目标20，页面分别显示实测值；模型推理速度是另一个指标 |
| 提示进程不完整/重复 | 先正常stop.sh再启动，保留日志用于定位，不执行killall java |

私有证据在runtime/validation/，服务日志在logs/，逐轮截图/动作在各实例episodes目录。提交问题时先删去私人笔记、路径和凭据，不上传完整私有备份。

## 6. 备份与恢复

```bash
./stop.sh
.venv/bin/python scripts/backup.py --full
.venv/bin/python scripts/backup.py --verify backups/backup-manifest-时间戳.json
```

公开源码包、Git历史bundle与完整私有包分别生成。完整包含模型、世界、背包、文档记忆、截图/日志、Python环境和登记的外部Java/游戏资源/llama.cpp，不能公开上传。历史完整快照不受升级影响。

恢复到**新的空目录**，不要覆盖仍在运行的项目：

```bash
mkdir minecraft-agent-restored
cd minecraft-agent-restored
tar --zstd -xf /安全路径/PRIVATE-minecraft-agent-full-时间戳.tar.zst
python3 scripts/restore_private.py --rebind
./setup.sh --doctor
./start.sh --paused --no-open
```

恢复脚本备份原本地配置并重绑定路径；可复用Python环境与外部Java/引擎。此包不是操作系统镜像，目标系统仍须提供兼容驱动、KWin、libei等系统组件。换发行版/架构可能需要重建 `.venv` 或原生库。本机临时目录恢复测试不代表跨机器恢复已经完成。

若要恢复Git历史，可在另一个空目录执行 `git clone /解压目录/restore-history.bundle 项目名`；源码和世界数据的恢复是两个流程。
