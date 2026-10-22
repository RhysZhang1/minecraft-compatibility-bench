# 适配问题记录

## 2026-10-22

- 原版 GTNH 服务器启动脚本固定 6 GiB 且退出后自动重启。测试副本改用单次受控启动，堆上限 4 GiB；绑定回环地址，便于监测并减少同机内存竞争。
- 原版客户端依赖清单包含继承的重复库。直接拼接会优先载入 Guava 15，导致 `CharSource.readLines` 缺失，进而让 Forge AccessTransformer 加载失败，出现多个模组 IllegalAccessError。启动器按 HMCL 语义以同名库最后版本覆盖（Guava 17），保留完整整合包。
- 旧版 `jinput-platform` 是仅提供原生库的依赖，没有普通 jar；启动器单独提取 Linux natives。
- 模型预算：原始 9B BF16 约 18.8 GB，无法给双 Java 进程留下足够余量；主方案采用对应检查点 Q4_K_M 与独立视觉投影。小模型官方文件作为格式与回退验证资料。
- 原始桌面 GTNH 和 HMCL 文件只读复用；实验发生于当前项目的 `instances/` 副本。
- 桥接采用客户端模组内的截图与按键绑定，不向整个桌面发送键鼠事件。
- GTNH 主菜单由 Custom Main Menu 替换成 `GuiCustom`；自动连接识别该菜单，并处理断线重连。
- 直接构造原版 `GuiConnecting` 绕过了 Forge 的握手初始化，导致 `playClientBlock` 空指针。改用 `FMLClientHandler.connectToServerAtStartup`，保留 Forge 正常握手链路。
- 背包/任务书界面需要将模型鼠标位移映射为 GUI 坐标并派发界面点击、释放、拖动与键盘事件；仅设置游戏 KeyBinding 无法完成 GUI 操作。
- mradermacher 9B-S1 Q4_K_M 转换文件包含 32 层主权重（blk.0–31），却声明 `qwen35.block_count=33`、`nextn_predict_layers=1`，没有第33层 MTP 张量。llama.cpp 报 `blk.32.attn_norm.weight not found`。保留原文件，在兼容副本中将两个元数据值改为 32 / 0；逐字节哈希验证所有 tensor data 不变，记录 `gguf-normalization.json`。这没有补造预测层或改写主模型权重。
- lwjgl3ify 的 `Mouse.setCursorPosition` 在桥接反射路径得到空 GLFW 窗口句柄。GUI 点击坐标改由桥接直接派发，并用客户端内的逻辑鼠标位置保持模型观测一致；不依赖操作系统鼠标输入。
- 修复 GGUF 主层数后，原有 recurrent_layers 数组仍长33。兼容副本保留该数组为未使用元数据，使用原文件的 full_attention_interval=4 推导32层模式，并验证它与原数组前32项完全一致；所有张量字节不变。
- 当前 llama.cpp 的媒体占位符含每次启动生成的随机部分，不能照文档示例硬编码 `<__media__>`。客户端从 `/props.media_marker` 获取实际值，否则报图像数量与标记数量不匹配。
- 原生 completion 接口会剥离 stop 字符串，当前版本通过 `stop_type=word`、`stopping_word` 返回终止原因。只有确认实际命中 `<|action_end|>` 时才恢复末尾标签；不能按另一个接口版本的 `stopped_word` 字段判断。
- BetterQuesting 自定义按钮不能只直接调用 GuiScreen.mouseClicked：改为向 lwjgl3ify 的客户端本地鼠标事件队列派发按下/释放；已实测任务书主页的 Quests 按钮进入 GuiQuestLines，书签按钮进入 GuiBookmarks。
- 单个33ms点击可能在下一帧前过期。包接收时立即执行第一子步骤，后续子步骤再按渲染事件计时。
- 监看进程重启时恢复已完成决策编号，不覆盖旧截图与输出；后续每个动作还记录实际客户端确认和执行后状态。
- 首批模型输出存在物品误识别，例如将任务书说成斧头；提示加入实际起始物品和由本机GTNH任务配置提取的数量要求。这是上下文适配，并没有通过训练消除误识别。
## 后台虚拟输入与隐藏窗口（2026-10-22补充）

原桥接已避免操作桌面鼠标，但真实 GLFW 回调、硬件按键轮询和窗口失焦仍可能影响测试客户端。新增只随专用客户端加载的 Java agent，在 lwjgl3ify 输入边界拦截真实事件，轮询只返回桥接持有的虚拟按键。GUI虚拟事件使用限定调用范围放行；共享状态由bootstrap类加载器加载，避免RFB与Forge持有两份状态。

逻辑鼠标抓取和坐标修改保留在客户端内，不再调用桌面抓取/移动；游戏调度使用虚拟焦点。创建 GLFW 窗口时设为不可见、不聚焦，保留 OpenGL 渲染上下文，截图继续送往8790。运行状态额外报告真实可见性、真实焦点、光标模式与拦截计数。

实际客户端验收：5种硬件回调被拦截，虚拟轮询/点击通过，无焦点隐藏状态下移动、转头、背包开关和截图变化均通过。当前不需要安装虚拟桌面，也不修改系统键鼠设置。

## 服务器命令窗口与游戏规则（2026-10-22补充）

- 新增 Minecraft 命令窗口和快捷按钮。使用回环RCON取得对应命令的实际回显，不通过操作系统终端执行用户输入。随机凭证仅存放在私有测试服务器属性文件；输入限制单行，HTTP接口检查来源、主机和JSON内容类型。
- Minecraft 1.7.10 RCON会关闭含合并请求包的连接。实测独立认证、发送一条命令并先读取首个回复，然后发送响应分界探针才兼容；后续继续拼接同编号输出，分界探针回显不进入用户结果。回归测试覆盖分片、UTF-8跨包、身份验证失败及断线。
- `server-settings.json`定义和平难度、非极限模式与死亡不掉落。启动前配置属性，观察服务检测新服务端进程后应用规则、读取keepInventory并save-all；已实测返回true，保存后的World/level.dat亦包含true。
- 手动命令默认暂停模型操作、清空截图历史并递增场景版本；正在推理的旧动作即使完成也不再执行。第69轮实际记录了旧动作丢弃，位置未受其W动作影响。暂停/恢复状态持久保存。
- UI命令与快速按钮已实际验证：在线玩家包含GameScalingBot，手动`/gamerule keepInventory`返回true，白天返回时间1000，晴天返回天气修改回显。
