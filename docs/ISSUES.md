# 适配问题记录

## 2026-10-22

- 原版 GTNH 服务器启动脚本固定 6 GiB 且退出后自动重启。测试副本改用单次受控启动，堆上限 4 GiB；绑定回环地址，便于监测并减少同机内存竞争。
- 原版客户端依赖清单包含继承的重复库。直接拼接会优先载入 Guava 15，导致 `CharSource.readLines` 缺失，进而让 Forge AccessTransformer 加载失败，出现多个模组 IllegalAccessError。启动器按 HMCL 语义以同名库最后版本覆盖（Guava 17），保留完整整合包。
- 旧版 `jinput-platform` 是仅提供原生库的依赖，没有普通 jar；启动器单独提取 Linux natives。
- 模型预算：原始 9B BF16 约 18.8 GB，无法给双 Java 进程留下足够余量；主方案采用对应检查点 Q4_K_M 与独立视觉投影。小模型官方文件作为格式与回退验证资料。
- 原始桌面 GTNH 和 HMCL 文件只读复用；实验发生于当前项目的 `instances/` 副本。
- 桥接采用客户端模组内的截图与按键绑定，不向整个桌面发送键鼠事件。
