# 迁移与环境

[English](PORTABILITY.en.md)

## 版本边界

| 客户端 | 输入/截图后端 | 只读状态 | 本机验证 |
|---|---|---|---|
| 原版1.7.10 / Java8 | 独立KWin/Xwayland/libei | 内置69项版本接口表 | 完整基础操作 |
| 原版1.20.1 / Java21 | 同上 | Mojang客户端映射 | 完整基础操作 |
| 原版1.21.1 / Java21 | 同上 | Mojang客户端映射 | 完整基础操作 |
| 原版26.3 / Java25，SDL/新渲染 | 同上 | 可读类名与GUI接口回退 | 完整基础操作 |
| GTNH2.8.4 / Minecraft1.7.10 | 原lwjgl3ify进程内输入 | 原Forge客户端桥接 | 保留旧实例并回归启动 |
| 其他Forge/Fabric整合包 | 可导入版本清单，复用独立会话 | 基础版本对应映射；自定义界面仍以画面为准 | 尚未逐包验证 |

这张表不把原版版本通过等同于所有整合包通过。现代模组加载器的继承清单、模块参数和自定义启动流程仍可能需要调整；整合包知识和模型策略不放入核心控制代码。

## 配置层次

- `instance-settings.json`：带占位符和说明的公开模板；首次克隆没有可运行实例。实际路径与世界标识由向导写入本地配置。
- `local-instances.json`：本机导入路径和覆盖项，Git忽略。原版测试服实际位置可以在桌面MC26.3，客户端/模型仍在本工作区。
- `local-settings.json`：本机Java、llama.cpp路径，Git忽略。环境变量 `MINECRAFT_JAVA_BIN`、`LLAMA_SERVER_BIN`、`LLAMA_CPP_SOURCE` 可覆盖。
- `game-settings.json`：公共资源基线；实例的resources再覆盖。GTNH仍为原来的服务器6G、客户端最高8G，原版测试服/客户端各最高4G。
- `control-settings.json`：新画面等待、历史长度和卡住恢复次数。没有未实现的时长旋钮。
- `model-settings.json`：2B/9B文件、显卡卸载与校验清单；当前2B配置未改。

同一实例重启保留world_id、角色名和UUID。新服务器/新世界应使用新的实例ID、world_id和记忆目录。错误复用记忆目录会被world.json标记拒绝。

向导可导入已有HMCL版本目录和独立服务器副本，保留原文件。启动器账号不参与导入。外部离线测试服可设为非托管，连接就绪可由客户端world_loaded状态确认，不依赖服务器RCON；没有RCON时命令窗口不可用。

## 从公开源码构建

先用系统软件包提供KWin、Xwayland、libei运行库/开发头、D-Bus开发头、C编译器、pkg-config、JDK、git、zstd。当前只在Linux x86_64/NVIDIA上执行了完整测试；其他系统未验证。

运行 `./setup.sh`：先“配置环境与依赖”，再“安装指定版本原版客户端、服务器与Java”，最后准备模型。Python安装在 `.venv/`；Java安装在 `instances/java/`；官方库/资源在 `instances/vanilla-runtime/`。下载可重跑，已存在文件会验证哈希。

需要重新编译只读采集器时，ASM使用core+tree两个库。源码发行包的release目录已有经过清单验证的本项目JAR；Git源码可通过向导下载ASM SDK，再运行 `scripts/build_sensors.py`。本地编译过的输入库与桥接JAR会随源码包附带；不同ABI应重新编译原生输入库。

2B转换需要先准备llama.cpp源码、转换依赖和官方固定revision检查点，向导会分别提示下载/转换/选中，避免不经意更换默认模型。CUDA构建依赖本机已有CUDA编译工具；CPU构建不需要CUDA。构建脚本只创建新目录，不重置已有llama.cpp仓库。

## 隔离与数据

KWin使用 `--virtual` 和独立D-Bus，XDG运行目录、配置/缓存/数据目录也独立。输入库校验目标D-Bus上的KWin进程就是该项目专属合成器，没有桌面会话回退。X11窗口按客户端进程标识定位，不依赖“Minecraft”标题。

按键和鼠标在虚拟会话内正常投递，游戏仍使用NVIDIA显卡。测试不要求人手同时操作硬件；记录的是专属显示/输入设备和真实客户端接收结果，没有声称完成人工键鼠对抗测试。

原版通道的Java代理只读，服务端无需桥接模组。读取失败会标记unknown或inventory_error，不能当作背包为空。26.3保留新的gamerule写法；1.7.10测试夹具用旧版支持的逐方块设置和实际鼠标转向，避免拿新版命令失败当成功。

声音未提供给模型；当前独立会话中可能使用游戏的静音回退，不影响本次视觉/动作验收。在线账户认证、自定义整合包任务接口、长期规划能力没有在这次基础兼容测试中完成。
