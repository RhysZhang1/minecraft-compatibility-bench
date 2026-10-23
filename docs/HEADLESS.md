# 没有桌面环境的服务器

本项目的 `virtual-x11` 通道不需要物理显示器或已登录的桌面。启动脚本自行创建 KWin 虚拟输出、私有 D-Bus 与 Xwayland；不依赖桌面已有的DISPLAY/WAYLAND_DISPLAY，也不要求完整Plasma桌面或显示管理器。

但它仍然要渲染**真实Minecraft客户端**：服务端、客户端和模型是三个不同进程。只有Java服务端的精简系统，需要补齐后台图形组件后才可运行视觉AI。

## 必需条件

- Linux x86_64；WSL/Windows状态见WSL.md。
- KWin 6，且实际提供RemoteDesktop/libei接口；Xwayland、D-Bus、libei、libX11。
- 可用的OpenGL/EGL渲染驱动。GPU推理和游戏图形是两条路径，CUDA可用不能代替游戏渲染验证。
- 无独显时可以尝试发行版提供的Mesa软件OpenGL，但性能、指令集和游戏版本适配须现场验证，不能保证精简系统开箱即用。
- Python，项目本地依赖，JDK/javac/jar，C编译器及libei/D-Bus开发文件，git、cmake、zstd。
- 对应版本Java和MC客户端/资源。后台客户端由工具准备或导入，服务端不能替代客户端。
- 运行模型的CPU/内存或兼容CUDA环境；工具不替使用者安装/更换显示驱动。

向导检测到缺失组件时，会展示当前发行版的软件包安装范围；是否执行由使用者选择。它不会添加不明软件源、安装完整桌面或自动升级发行版。老发行版仓库可能只有KWin5或缺少libei，不能仅靠安装命令推定兼容；向导会停止并说明缺项。

不同发行版可能拆分KWin插件、Mesa、Qt平台插件等包。工具存在不等于图形链路通过：最终必须实际启动私有会话，并读到客户端新画面、界面状态和隔离输入确认。

## 操作入口

```bash
./setup.sh --inspect-server /srv/minecraft
./setup.sh --server-dir /srv/minecraft
./start.sh --instance 实例ID --paused --no-open
```

从远程电脑用SSH转发8790端口，在自己的浏览器查看。服务器上不需要浏览器；`--no-open` 禁止尝试打开浏览器。观察台不直接监听公网。

## 验证边界

本机无桌面会话环境变量启动验收，与一台全新、未安装任何图形包的服务器不是同一项测试。前者验证后台通道不依赖现有桌面会话；后者仍需要目标发行版、驱动和软件包实际验收。项目不会通过连接到用户桌面的共享输入设备来绕过缺失的后台组件。
