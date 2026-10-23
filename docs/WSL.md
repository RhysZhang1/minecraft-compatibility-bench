# WSL支持状态

[English](WSL.en.md)

**当前未完成WSL端到端适配，也没有WSL实机测试。v0.1.0只声明Linux本机验证通过。** 本机测试环境是Arch Linux，不能据此宣称Windows或WSL已经可用。

| 环境 | 当前状态 |
|---|---|
| Linux本机 x86_64 / KWin / NVIDIA | 已完成四版本基础操作与完整启停测试 |
| WSL1 | 不支持当前本地GUI控制通道；微软的Linux GUI支持要求WSL2 |
| WSL2 + WSLg | 可作为后续适配目标，尚未验证游戏、私有合成器、输入隔离与GPU渲染完整链路 |
| Windows原生 | 未提供对应的后台输入/截图后端与启停入口 |

微软的WSLg支持X11/Wayland GUI与加速OpenGL；NVIDIA也提供WSL2 CUDA支持。因此**模型计算或单个GUI程序可运行**不能直接证明本项目整套后台控制已经兼容。

当前最需要验证的部分是独立KWin虚拟会话、Xwayland、libei私有输入，以及Minecraft在该会话中的实际渲染。现有脚本主动清除桌面DISPLAY/WAYLAND_DISPLAY并创建自己的会话；不会为了启动成功而改用Windows桌面或共享WSLg输入目标。WSL的CUDA可用性与Minecraft图形渲染应分别检查。

安装检测目前是Linux工具/路径检测，没有完整WSL诊断流程；WSL中的nvidia-smi可能位于/usr/lib/wsl/lib/nvidia-smi。NVIDIA官方要求WSL使用Windows宿主提供的驱动，不要在WSL中另装Linux显示驱动。

要把WSL2列为已支持，需要在真实Windows/WSL2机器上验证：

- 环境检测、Java/模型/客户端安装与中断重试。
- 私有合成器、Xwayland、输入设备与实际渲染，不接受输入落入共享桌面的回退。
- 移动、背包、持续挖掘/拾取、暂停释放，以及Windows键鼠同时使用时的隔离。
- 模型CPU/GPU模式、游戏渲染、网页预览和性能分别记录。
- 从Windows浏览器查看观察台、重复启停、取消启动、后台残留进程、世界/角色与记忆保存。

当前没有上述实机证据，因此不提供“保证可运行”的WSL安装命令，也不把WSL2加入已验证平台列表。

参考：[微软WSLg说明](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)、[NVIDIA CUDA on WSL指南](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)。
