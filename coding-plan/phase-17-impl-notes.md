# Phase-17 实施笔记（进度存档，防上下文丢失）

## 任务
修复 phase-17 三缺口：A 编排打通 / B 记忆语义化 / C 自动迭代前置（C 只验收前置，不改码）。
工程根：/home/harry/work/core-agent

## 已确认代码锚点（带行号）

### A 编排
- `src/core/orchestration/router.py`：`match()` 无命中 `return self._fallback`（L43）；`handoff(target, TaskHandoff) -> await loop.arun(task)`。
- `src/core/runtime.py` L195-199：`main_agent = AgentProfile(agent_id="main", capabilities=["default"], loop=loop)`；`MultiAgentRouter([main_agent], fallback=main_agent)`。
- `src/core/orchestration/scheduler.py` `_run_subtask` L366-371：match 返回 None 时已 `SubtaskOutcome(ok=False, error=NO_AGENT_MATCH, reason="无匹配 Agent")`。
  => 核心修复 = runtime 不传 fallback + 注册子 agent 池 + 主 loop 注入 delegate 工具。

### B 记忆
- `src/core/runtime.py` L144：`backend = memory_backend if memory_backend is not None else FileBackend()`（path=None → 纯内存不落盘）。
- `src/core/loop/default.py` `remember` L265-278：只写 `轨迹 {trace_id}: {len(trajectory)} 步`。
- `src/core/memory/store.py`：`read(query, budget=4096)` 空 query 时 `backend.search("")` 全量 + relevance 排序 + truncate。
- `MemoryEntry` 无 session_id 字段。

### 关键机制
- `DefaultLoop.act` L224-235：`await self._tools.ainvoke(tool_id, args, trace_id=..., approved=...)`。
- `observe` L255-263：`result.data` 是 dict 且含 "reply" → `ctx.reply` + `ctx.finish()`（delegate 返回 dict 含 reply 可收口）。
- provider._call 支持 async handler（isawaitable 桥接）→ delegate 工具可用 async handler `await router.handoff(...)`。
- ToolDef 字段：tool_id/description/schema/coeffects/reversible/timeout_s/max_output；Tool=definition+handler+undo。
- ToolProvider：register / active_tools / ainvoke。

## 实现顺序（A→B→C）
1. router.py match() 无命中返回 None（不静默回落）。
2. runtime.py：注册 3 个子 agent（coding/research/review，各 DefaultLoop），无 fallback；主 loop 注入 delegate 工具（async handler 调 router.handoff）。
3. memory：MemoryEntry 加 session_id；backend search 语义打分（词元重叠）+ 默认落盘 path；store read 支持 session 过滤；default.py remember 写真实对话语义。
4. tests 同步。

## 待确认（下步读）
- DefaultLoop 的 planner 类位置（疑 core/loop/planner.py），reason/_tool_schemas 是否动态读 active_tools()。
- runtime L144-201 tools/planner/loop 构造细节。
- protocol.py MemoryEntry 字段定义（L1-79）。
- backend.py search 实现（L16-66）。
- tools/provider.py register 链路 + builtin.py schema 格式。

## 门禁
ruff + pyright + pytest 全绿；单次提交 `fix(orchestration+memory)`。

## 最终实现结果（2026-10-04 收口）

### 源码 7 处改动
- `router.py`：`match()` 无命中**抛** `OrchestrationError(NO_AGENT_MATCH)`，不再静默回落。
- `scheduler.py`：`_run_subtask` 用 `try/except OrchestrationError` 捕获，产出 `SubtaskOutcome(ok=False, code=NO_AGENT_MATCH)`。
- `runtime.py`：注册 3 个子 agent（coding/research/review，各带 DefaultLoop）；`MultiAgentRouter` **不传 fallback**；主 loop 注入 `tools.delegate` 工具（async handler 调 `router.handoff`）。
- `loop/default.py`：`remember` 从「只写轨迹 ID」改为写入真实对话语义（供语义检索）。
- `memory/protocol.py`：`MemoryEntry` 加 `session_id` 字段。
- `memory/backend.py`：`search` 增加语义打分（词元重叠）+ `FileBackend` 默认落盘。
- `entry.py`：noqa 遗留修正 `PLR0913` → `PLR0913, PLR0917`（顺带，非 phase-17 主体）。

### 测试契约同步（3 处）
1. `runtime.py` delegate `tool_id="delegate"` → `"tools.delegate"`（对齐 ToolDef 命名规范）。
2. `tests/test_phase13.py`：期望工具集合补 `"tools.delegate"`。
3. `tests/test_orchestration.py`：`test_match_raises_when_no_hit_no_fallback` —— 断言从 `is None` 改为 `pytest.raises(OrchestrationError)` 且 `code == NO_AGENT_MATCH`。

### 门禁
- pyright 0 errors；ruff `All checks passed!`；pytest `574 passed`。

### 关键教训
- `match()` 无命中的契约在 phase-17.md L33 已明确「抛 NO_AGENT_MATCH」，但测试沿用旧「返回 None」期望 → 必须同步测试，不能只改实现。
- runtime 装配段 `main_agent` 原本只在构造 `MultiAgentRouter([main_agent], fallback=main_agent)` 时使用；改成无 fallback + 子 agent 池后，需按能力（capabilities）注册，主 loop 通过 delegate 工具委托。
- ruff 报错需先判归属（runtime 两处是新引入、entry 一处是 phase-9 noqa 遗留），避免误改他人代码。
