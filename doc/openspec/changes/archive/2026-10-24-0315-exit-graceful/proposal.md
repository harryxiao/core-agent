# Proposal — TUI 优雅退出 `/exit`（0315）

## Why

change 0314 让 Ctrl+Q **不等待**在途阻塞工作（实测 42.4s → 0.36s），代价是退出即放弃后台
线程。用户据此提出两点：

1. 「记忆写需要等吗，怕退出未完成收尾」—— 需要说清哪些写入已在轮内落盘、哪些可能被放弃；
2. 需要一条**主动**的优雅退出路径：先保存会话记忆，再正常退出。

代码事实：每轮主记忆写（转录、`remember` 的 episodic、技能反馈、沉淀）在 `loop_finished`
之前**同步**完成，且记忆文件为 tmp + `os.replace` 原子提交（change 0206）—— 不会半写损坏。
但轮末**后台收尾链**（`_schedule_post_turn` → `_notify_turn` + `_maintain`，含会话压实 /
遗忘，change 0296）在 `loop_finished` **之后**挂为异步 task：退出瞬间它可能仍在途，被
`_close_loop` 取消、线程被放弃 ⇒ 本次会话的压实/遗忘未完成（数据不丢，但收尾未做）。

## What Changes

- 新增 TUI 斜杠命令 `/exit`（真源 `_COMMANDS`）：无在途轮次时，显示「正在保存会话记忆…」，
  **有界等待**本会话轮末后台收尾链收束，然后 `app.exit()` 正常退出；
  - 收束成功 ⇒「会话记忆已保存，退出」；
  - 超时 / 异常 ⇒ 明示「记忆收尾超时（已尽力保存），退出」后**仍退出**（不挂死）。
- 新增 `DefaultLoop.flush_post_turn()`：公开收尾接缝，等价于既有 `_await_post_turn(
  timeout=self._post_turn_wait_timeout)`（缺省 120s，零新配置键）。
- 新增 `UIAPILayer.flush_post_turn(session_id)`：会话校验 + 鸭子类型委托
  （循环未实现该方法 ⇒ 视为无在途收尾，返回 `True`）。
- 有在途轮次时 `/exit` **拒绝并提示**（「本轮进行中：等本轮结束后再 /exit，或 Ctrl+Q 立即
  退出」），不排队、不放弃本轮。

`/exit` 不接受参数。Ctrl+Q / Ctrl+C 的立即退出语义**逐字不变**（0314）。

## Impact

- 规格：`ui` **ADDED ×1**（TUI 优雅退出 `/exit`）。
- 代码：`src/core/loop/default.py`（公开接缝）、`src/core/ui/api.py`（委托）、
  `src/core/ui/repl.py`（命令登记 + 分发 + 收尾协程）。
- 测试：新增 `tests/test_exit_graceful.py`（loop + API）；`tests/test_repl.py` 增 `/exit`
  行为用例并更新浮层命令清单。
- 文档：ADR-0305、known-risk E251、test-cases §228、ui-interface 段落。

## Out of Scope

- 不改 Ctrl+Q / Ctrl+C（立即退出仍是逃生口），不改 0314 的 `_close_loop` 语义。
- 不新增配置键；不做「退出前无限期等待」。
- 不写会话结束标记 / 不额外调用 `memory.compact`（压实已由轮末维护链承担，重复调用会因
  压实锁直接跳过）。
- 不改计划审批 / 工具审批挂起期的输入分流（仍须先 y/n；Ctrl+Q 仍是逃生口）。
