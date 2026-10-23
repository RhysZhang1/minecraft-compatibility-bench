# 开发与架构

[English](CONTRIBUTING.en.md)

本项目负责兼容与测评，不定义模型能力。修改应区分模型输出、解析结果、客户端确认、观测变化和任务完成；后两者不能等同。注释、文档字符串和新增标识符使用英文；用户界面文字可按本地化需要使用中文。

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check mcbench scripts tests
.venv/bin/ruff format --check mcbench scripts tests
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mcbench replay tests/fixtures/golden/replay.json
.venv/bin/python -m build --wheel
```

| 模块 | 职责 |
|---|---|
| mcbench/runtime.py | 显式创建状态、锁、取消 epoch、依赖与工作线程 |
| mcbench/loop.py | 顺序推理、动作确认、新画面、记忆调度 |
| mcbench/prompt.py | 检查点协议、图片历史、固定前缀与实时上下文 |
| mcbench/feedback.py | 纯观测比较、空动作与界面循环计数 |
| mcbench/decisions.py | 无副作用的执行门槛和恢复/暂停决策 |
| mcbench/http.py | 本地 HTTP 路由、请求边界与界面资源 |
| mcbench/services.py | RCON 命令、进程资源、GPU 遥测与状态快照 |
| mcbench/memory.py | 按世界的事实、用户笔记及未确认建议 |
| mcbench/tools/ | 部署、环境准备、构建、启停与备份实现 |

Runtime 显式组合 PromptBuilder、DecisionLoop 和 RuntimeServices，每个对象持有同一运行实例引用；没有跨模块全局状态单例。模块导入不读取实例或创建线程。scripts/ 的短启动器保留旧命令，切换到项目模块运行，无 sys.path 修改。安装后的 wheel 可从其他目录使用回放 API；真实游戏工具还需要包含 Java/C 源码与配置的源码工作区。

必须保留：解析成功之外还验证 enabled/epoch/session；动作完成确认之后才接受匹配会话的新画面；暂停、断线、目标变化与心跳过期必须释放挖掘；只有 LB 可在规定条件下延续，不能延续移动键。恢复只重观察/清理历史/有限次数后暂停，不替模型点击。未知传感器值不能视为空背包。

新测试用例应固定预期结果并说明来源，不能在测试运行时调用当前代码更新 expected。真实记录与人为边界构造分开标记。详见 tests/fixtures/README.md。CI 运行纯离线回放与 wheel 外部安装检查；真实游戏验收仍需记录实际平台与版本。

自有代码采用 GPL-3.0-or-later。vendor 不做格式化或许可替换；Java -javaagent 是 JVM 的标准参数，与产品定位无关。请勿提交世界、模型、路径凭据、私人记忆与原始运行目录。
