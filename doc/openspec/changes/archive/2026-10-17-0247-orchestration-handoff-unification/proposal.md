# Proposal — TaskHandoff 统一执行框架（change 0247）

## 为什么

只读盘点（`/tmp/orchestration-review.txt` P1-9）确认：规格 R3 承诺「通过 TaskHandoff 交接，
交接上下文由 context 模块打包」，实现却有三套互不相通的执行路径：

1. `TaskScheduler._run_subtask` **直连** `profile.loop.astream(goal)`（`scheduler.py:712-724`），
   构造 `TaskHandoff` 的代码**不存在** —— `context_pack` / `acceptance` / `deadline` /
   `priority` 四个字段在产线**零消费**。
2. `MultiAgentRouter.handoff` 只被 beast 使用，且只消费 `task` / `session_id` 两字段；
   `deadline` 全仓无消费方，子任务可无限挂起。
3. 交接上下文只是字符串拼接（`_handoff_goal`），无总预算；beast 在 `handoff` 抛错时
   **不会** `recall`，会话滞留 `ACTIVE`。

## 改什么

- 新增共享执行器 `src/core/orchestration/handoff.py`：
  `build_context_pack`（纯函数、token 有界）/ `render_handoff` / `stream_handoff` /
  `run_handoff`。beast / pet / scheduler 复用同一份框架代码。
- `MultiAgentRouter` 增 `handoff_stream`，`handoff` 委托 `run_handoff`；
  两者均消费 `TaskHandoff` 全字段（`deadline` 用 `asyncio.timeout` 生效）。
- `TaskScheduler._run_subtask` 构造 `TaskHandoff`（task / context_pack / acceptance /
  deadline / priority / session_id 全字段）并经 `router.handoff_stream` 执行；
  保留 `subtask_progress` 流式回流与终态归一。
- 新增错误码 `SUBTASK_TIMEOUT`；超时归一为子任务失败，进入 0246 的恢复回路。
- 新增配置 `orchestration.subtask_timeout`（秒，默认 `0` = 不设限）；ConfigSpec 三面 +
  校验期拒绝非法值 + 组合根注入 + `config set` 白名单。
- beast `summon` 的 `session.recall()` 移入 `finally`（异常/超时也回归）；
  pet `wake` 经 `run_handoff` 执行（空上下文 ⇒ prompt 逐字相同）。
- `core/loop/protocol.py` 新增 `current_session_id` ContextVar，`DefaultLoop` 在 `_act`
  前后 set/reset；`runtime._dispatch` 读取并透传子 Agent `arun(..., session_id=...)`
  ⇒ 委托轨迹归入发起会话。

## 影响面

- 新增 `src/core/orchestration/handoff.py`
- `src/core/orchestration/{router,scheduler,errors}.py`
- `src/core/configuration/manager.py`、`src/core/entry.py`
- `src/core/beast/manager.py`、`src/core/pet/core/session.py`
- `src/core/loop/{protocol,default}.py`、`src/core/runtime.py`
- 规格：`orchestration` R3 **MODIFIED**、`configuration`「编排调度配置」**MODIFIED**
- 文档：`03-interfaces/{orchestration,configuration}-interface.md`、`02-modules/{orchestration,beast-mode,pet-mode}.md`
- 测试：新增 `tests/test_orchestration_handoff.py`；beast/pet/loop/config 各补用例

## 不做

- 不合并 beast 的专属 router 与主 router（能力集合不同，合并不带来收益）。
- 不为 `AgentProfile` 增加 `session_scope`：执行器只**转发** `session_id`，不解释其语义；
  主任务 / beast / pet 各自填对。
- 不改 `exclude_source_prefixes=("beast.","pet")`，不改任何 `source` / 会话命名空间。
- 不新增 `resolve` API（无消费方）。
