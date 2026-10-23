# Minecraft Compatibility Bench

为视觉动作模型提供连接真实 Minecraft 客户端的兼容层与测评台。当前接入 GameScaling；模型的能力与上限由上游检查点决定，本项目提供输入输出适配、运行管理与可复现的行为回归。提供后台键鼠隔离、游戏预览、动作反馈、服务器检测、模型推荐、部署向导和按世界保存的文档记忆。

[English](README.md) · [安装与排障](docs/INSTALL.md) · [已有服务器部署](docs/SERVER-DEPLOYMENT.md) · [无桌面运行条件](docs/HEADLESS.md) · [版本范围](docs/PORTABILITY.md) · [WSL状态](docs/WSL.md)

## 能在没有桌面环境的服务器上运行吗？

**可以在无显示器、没有登录桌面会话的 Linux x86_64 服务器上运行，但必须安装后台图形运行组件。** 不要求安装完整桌面、桌面面板或显示管理器。

模型通过真实客户端画面操作游戏，因此运行时仍然需要一个隐藏的 MC 客户端。仅有 Java 和 MC 服务端还不够：

| 环境 | 用途 |
|---|---|
| KWin 6（需具备RemoteDesktop/libei接口）、Xwayland、D-Bus、libei、libX11 | 建立私有后台显示与输入通道 |
| 可用的 OpenGL 驱动，或兼容的 Mesa 软件渲染 | 绘制客户端；没有显示器也需要渲染能力 |
| Python、JDK、C/C++编译工具、pkg-config | 运行兼容层，构建状态采集和输入组件 |
| 对应版本的 Java、MC 客户端及游戏资源 | 让 AI 作为玩家连接服务器 |
| llama.cpp 与模型文件；GPU推理另需兼容CUDA环境 | 运行视觉模型；也可选择CPU推理 |

软件渲染和CPU模型可能很慢，实际可用性以启动检查和真实客户端画面为准。WSL2、Windows原生和其他发行版组合不能由本机Linux测试直接推定支持。详见[无桌面部署说明](docs/HEADLESS.md)。

## 给已有服务器添加视觉模型客户端

```bash
git clone https://github.com/RhysZhang1/minecraft-compatibility-bench.git
cd minecraft-compatibility-bench

# 先只读检测硬件、服务器配置与推荐方案
./setup.sh --inspect-server /你的服务器目录

# 交互式确认方案并部署
./setup.sh --server-dir /你的服务器目录
```

向导会检测内存、可用显存、工具与运行库、游戏版本、服务端类型、端口、认证、白名单和资源设置。预留原服、客户端与系统资源后，在当前可自动准备的2B/9B模型中推荐运行方式；推荐是保守估算，不是性能承诺。

确认后准备项目内Python、llama.cpp、匹配客户端/Java、模型和独立记忆。缺失系统依赖时，先展示软件包安装范围，再由使用者选择执行；不安装显卡驱动，不自动升级发行版。

默认只连接已有服务器，不改原服文件、不接管原服进程。也可在原服停止后创建独立托管副本。整合包需要匹配客户端；在线认证尚未接入，工具不会自动关闭认证。检测与部署细节见[服务器部署指南](docs/SERVER-DEPLOYMENT.md)。

## 启动、观察与停止

```bash
./start.sh --instance 你的实例ID --paused --no-open
./stop.sh
```

观察台：<http://127.0.0.1:8790/>。它显示实际画面、模型真实输出、动作反馈和续玩记忆，可暂停/恢复AI。接入原服时保留原服设置；托管测试副本才默认应用和平和死亡不掉落。

模型卡住时，使用**临时手动干预**区：开启画面点击/拖动，或用面板按钮发送短时按键。干预会暂停模型并作废尚未执行的旧动作；**释放全部输入**用于中断长按，**交还模型**让模型重新观察后继续。输入仍限定在私有游戏显示中。[操作说明与后端限制](docs/INTERVENTION.md)。

在另一台电脑查看时可使用SSH转发：

```bash
ssh -N -L 8790:127.0.0.1:8790 用户名@服务器地址
```

然后在自己的浏览器打开上面的本地地址。观察台默认仅监听回环地址，不直接暴露到公网。

`start.sh` 会使用所选实例保存的模型与CPU/GPU建议。`--profile cpu` 可显式改为CPU推理；切换已运行模型/模式前先停止。`stop.sh` 保存AI记忆并停止本项目进程；仅接入模式下，原服务器继续由原有方式运行。

## 记忆与已验证范围

同一实例保持固定角色名和离线UUID，物品与位置由对应服务器保存。目标、长期笔记和整理建议写入独立世界的文档；重启读取这些文档，不声称模型进程中的上下文本身跨进程保留。已确认事实与模型建议分别标注。

本机已验证原版 **1.7.10、1.20.1、1.21.1、26.3** 的移动、背包、持续挖掘/拾取及暂停释放。支持后台运行不代表模型能完成复杂合成、任意模组任务或长期规划。[基础验收](docs/VANILLA-VALIDATION.md)、[发布检查](docs/RELEASE-CHECKS.md)。

## 许可与来源

本项目自行编写的兼容层、工具与界面采用 **GPL-3.0-or-later**，见 [LICENSE](LICENSE) 与[许可范围](LICENSING.md)。第三方代码、依赖、模型和游戏资源保留各自原许可：包括 `vendor/GameScaling` 的 Apache-2.0、ASM 的 BSD-3-Clause、libei 的 MIT。模型权重与Minecraft文件不随源码发布。

上游：[GameScaling](https://gamescaling.github.io/) · [模型](https://huggingface.co/THUSI-Lab/GameScaling) · [论文](https://arxiv.org/abs/2610.28698) · [llama.cpp](https://github.com/ggml-org/llama.cpp)。

## 开发与离线回放

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mcbench replay tests/fixtures/golden/replay.json
```

公开的 `instance-settings.json` 只提供带占位符和 `_comment` 说明的模板，不自动启用任何实例；向导把实际路径写入忽略上传的 `local-instances.json`。首次克隆后需先配置实例。

标准 Python 包在 `mcbench/`：`loop` 编排决策，`prompt` 保留检查点格式，`feedback` 比较观测，`http` 提供本地界面；状态由显式创建的 `Runtime` 持有。回放包含脱敏真实画面、原始输出及明确标注的边界用例，零 GPU、零 X11，不重新运行模型，也不评判任务能力。[开发指南](docs/CONTRIBUTING.md) · [配置模板](docs/CONFIGURATION.md) · [回放说明](tests/fixtures/README.md)。
