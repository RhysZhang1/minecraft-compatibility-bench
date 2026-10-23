# Minecraft GameScaling Agent

[安装与排障](docs/INSTALL.md) · [适配范围](docs/PORTABILITY.md) · [基础验收](docs/VANILLA-VALIDATION.md) · [发布前审查](docs/RELEASE-CHECKS.md)

以原版 Minecraft 为基线，把视觉模型接到真实游戏客户端。模型只根据画面和观测生成动作；兼容层负责后台输入、截图、动作确认、反馈、记忆与启停。

**本机已实际测试原版 1.7.10、1.20.1、1.21.1、26.3。** 当前模型仍为 GameScaling-2B-S1 Q4_K_M + F16 视觉编码器，使用 llama.cpp；本次没有换模型，也没有增加 GTNH 专用玩法提示。现有 GTNH 副本和旧后端保留为独立实例。

观察台：<http://127.0.0.1:8790/>。其中显示真实游戏画面、模型实际输出、动作反馈、服务器命令与续玩记忆，也可以选择已安装实例并保存切换。

## 日常使用

```bash
./start.sh                 # 从完全停止状态启动上次实例，默认使用显卡推理
./start.sh --paused        # 先启动并连接，保持模型暂停
./stop.sh                  # 保存世界、记忆，停止本项目全部服务
./start.sh --profile cpu   # 模型放CPU/内存，游戏继续使用显卡
```

指定实例：

```bash
./start.sh --instance vanilla-1-20-1
./start.sh --instance vanilla-1-21-1
./start.sh --instance vanilla-26-3
./start.sh --instance vanilla-1-7-10
./start.sh --instance gtnh
```

切换前先停止；观察台的“切换（暂停启动）”会自动完成保存、停止和重新启动。角色名/离线UUID、服务器世界和背包保存在各自实例中，记忆、目标和动作记录也按实例分别保存。模型上下文不跨进程保留，重启时读取保存的文档记忆。

## 在另一台机器准备

从零安装的顺序、依赖、EULA、恢复和常见错误请先看 **[完整安装说明](docs/INSTALL.md)**。入口是交互式向导：

```bash
./setup.sh
./setup.sh --doctor        # 只检测，不下载、不改当前模型
./setup.sh --verify-models # 同时完整校验已存在模型
```

向导提供环境检测与路径配置、项目内Python依赖、模型检测/下载/转换、实例导入、官方原版客户端/服务器/Java安装、固定版本llama.cpp构建、源码或完整私有备份。下载模型不自动切换正在使用的模型。

原版共用后端运行在 **Linux + KWin虚拟输出 + Xwayland + libei** 上，本机验证为KWin 6.8 / NVIDIA。需要系统提供这些组件，以及libei、D-Bus和C编译工具；源码构建只读采集器还需要JDK和ASM。向导不会替换系统Java、Python或显卡驱动。发行版组件的安装仍需按对应系统的软件包管理方式完成。

原版客户端、库、资源和Java从Mojang官方清单下载，逐文件验证SHA1；模型固定Hugging Face revision并验证SHA256。1.7.10使用项目内Java8，本机1.20.1/1.21.1使用Java21，26.3使用Java25。向导按官方清单准备对应运行时。

源码归档附带已编译的本项目桥接文件；直接从Git源码构建时，可在向导准备ASM依赖。详见 [迁移与依赖](docs/PORTABILITY.md)。

服务器安装可以复制你已有的EULA接受记录；脚本不会生成新的接受记录。测试服仅监听本机，使用专用离线角色。现有启动器账户文件不会被读取；正版账户登录/在线认证服务器未接入。

## 兼容方式

原版通道使用独立、无桌面窗口的KWin会话，内部客户端保持正常窗口和显卡渲染。键鼠发送到这套会话的私有输入设备，截图只读取其中的Minecraft窗口；你的桌面显示、键鼠和D-Bus会话不作为输入目标。游戏帧率上限60，预览目标20FPS，实际帧率单独显示。

可选Java采集器只读取当前界面、位置、生命、背包和目标方块。新版本优先使用官方映射，1.7.10使用69项API名称表；采集器不负责点击任务按钮、选择配方或替模型决策。服务端不需要安装桥接模组。现有GTNH后端仍使用lwjgl3ify专用进程内输入隔离。

动作保持论文的六子步/200ms格式。连续挖掘可在同一目标上延续左键，遇到目标变化、GUI、暂停、心跳失效或连续10秒上限就释放。移动键按动作包边界释放。模型的下一步必须读取动作确认之后的新画面。

通用反馈会说明上一动作是否改变位置、界面、背包或可见场景，合并重复空动作历史，检测反复开关同两个界面，并在有限次重新观察仍无变化时保留现场暂停。这里的“画面变化”不等于“完成目标”。

## 测试与现状

四个原版版本都实际通过了移动/转向、背包开关、持续挖掉泥土、拾取、暂停释放测试；不是仅检查文件或服务器端口。可在内置独立测试世界重跑：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/verify_virtual.py
```

26.3的一段自主运行共88轮，88轮解析并执行成功；推理中位数约1.35秒、决策周期中位数约1.67秒，4轮为空动作。模型自行挖掘使泥土从1个增至16个。复杂合成、跨模组任务和长期规划仍需能力评测；这段原版记录与旧GTNH场景不是严格A/B对照。

详细记录：[原版验收](docs/VANILLA-VALIDATION.md)、[适配问题](docs/ISSUES.md)。之前的论文/GTNH部署过程和旧验证数据保留在 [GTNH实验记录](docs/GTNH-EXPERIMENT.md) 与 [历史验证](docs/VALIDATION.md)。

## 备份与以后上传GitHub

```bash
./stop.sh
.venv/bin/python scripts/backup.py --full
.venv/bin/python scripts/backup.py --verify backups/backup-manifest-时间戳.json
```

`minecraft-agent-source-*.tar.gz` 是可公开的源码包，包含交互式脚本、版本配置、文档和本项目编译的桥接文件；`minecraft-agent-history-*.bundle` 保存本地Git历史。

`PRIVATE-minecraft-agent-full-*.tar.zst` 是私有完整快照：全部模型、世界与角色、记忆、动作截图/日志、本地路径配置、Python环境，以及登记的外部游戏资源、Java和llama.cpp。还包含桌面MC26.3下登记的测试服。该包保留私有数据，不作为GitHub源码上传。校验清单记录每个归档的大小和SHA256。

完整包解压到新目录后可运行 `python3 scripts/restore_private.py --rebind` 重绑定路径，再通过向导检测。恢复仍依赖本机系统图形驱动/KWin/libei；离线恢复与公开源码重新安装是不同流程。公开仓库只包含源码、配置模板和文档；模型、存档、私人笔记及运行日志均保留在本地。

## 来源

- [GameScaling项目](https://gamescaling.github.io/)、[代码](https://github.com/THUSI-Lab/GameScaling)、[模型](https://huggingface.co/THUSI-Lab/GameScaling)、[论文](https://arxiv.org/abs/2610.28698)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)，本机固定commit见 `scripts/build_engine.py`
- GameScaling推理代码保留原Apache-2.0许可；桥接使用ASM（BSD-3-Clause），私有会话输入链接libei（MIT）。见 `THIRD_PARTY_NOTICES/`。模型、Minecraft及整合包资源各自保留原许可。
