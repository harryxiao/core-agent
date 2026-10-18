# Proposal 0269 — 钩子实现（E101）

## Why

`doc/openspec/specs/hooks/spec.md` 已于 change 0164 / ADR-0155 定下 7 个事件、两种形态、
失败矩阵与安全边界，但**契约先行、尚未实现**（台账 E101）。当前操作者要挂一个
「工具执行前跑策略脚本」只能在组合根改 Python 代码并重打包；hooks 是 Claude Code 对齐
面里最大的一块自动化缺口。

## What Changes

- 新增 `src/core/hooks/`：事件模型（`HookEvent` / 载荷脱敏）、执行器（argv 子进程 +
  内置回调、超时、有界输出、白名单环境）、注册表（按事件与 `match` 收窄）。
- `DefaultLoop` 新增两个对称的同步注入点：`turn_before`（可否决）与 `turn_after`
  （只留痕）；动作前链 / 结果侧观察者扩展为可等待（支持异步钩子，既有同步实现逐字不变）。
- `MemoryStore` 新增 `write_observer` DI 形参（只观察、不可否决）。
- 配置面：`hooks.enabled` / `hooks.timeout_s` / `hooks.on_error` 三个 ConfigSpec 标量；
  `hooks.entries` 清单只从 `config.yaml` 结构化段读取。扩展 `_parse_yaml_subset` /
  `_dump_yaml` 支持块序列与行内 flow 序列/映射（否则清单无法表达）。
- 组合根把 hooks 接到主 / 子 Agent / 神兽 / 宠物四个 loop 与共享 `MemoryStore`；
  `session.start` 在会话首轮前幂等触发，`session.end` 经 `atexit` 收尾。

## Impact

- 代码：`src/core/hooks/`（新）、`src/core/loop/{default,protocol}.py`、
  `src/core/memory/store.py`、`src/core/configuration/manager.py`、`src/core/runtime.py`。
- 测试：新增 `tests/test_hooks.py`、`tests/test_configuration.py` 补 YAML 序列用例。
- 文档：hooks 规格状态、loop 规格「横切中间件插入」、ADR、台账、测试节、模块文档。
- 兼容：`hooks.enabled` 缺省关 ⇒ 四个 loop 与 `MemoryStore` 注入面均为 `None`，
  既有行为逐字不变；同步中间件 / 观察者签名不变。

## 不做（明确边界）

- 不引入事件总线；不做同事件多钩子的权重 / 否决覆盖（按声明序，任一 before 阻断即终局）。
- 不做钩子副作用回滚（规格明示的**唯一**可逆性例外）；不把 stdout/stderr 写进日志 / 记忆 / 对话。
- 不给 `hooks.entries` 提供 CLI flag / 环境变量形态。
- 不覆盖 Web / Desktop 的独立会话边界（`session.end` 依赖进程退出；中途显式结束另议）。
