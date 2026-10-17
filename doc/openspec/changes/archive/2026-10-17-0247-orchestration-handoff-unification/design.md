# Design — TaskHandoff 统一执行框架（change 0247）

## D1 共享执行器

新增 `core/orchestration/handoff.py`（orchestration 不 import beast/pet，beast/pet import
orchestration —— 既有分层方向）：

```python
MAX_HANDOFF_CHARS = 2000          # 单字段字符上界（沿用 scheduler 既有口径）
DEFAULT_CONTEXT_TOKENS = 2000     # 上下文包总 token 预算（estimate_tokens 估算）

def build_context_pack(goal, dependencies, *, max_tokens) -> dict[str, Any]
def render_handoff(handoff: TaskHandoff) -> str
async def stream_handoff(loop, handoff, *, deadline=None) -> AsyncIterator[LoopEvent]
async def run_handoff(loop, handoff, *, deadline=None) -> LoopResult
```

- `build_context_pack`：`{"goal": str, "dependencies": [{"id","goal","result"}]}`。
  按依赖顺序装入；每条先扣 id/goal 头部预算，结果按剩余预算用 `estimate_tokens` 截断；
  任一条被截断即停止装入（后续依赖不再进包）。单条字段另受 `MAX_HANDOFF_CHARS` 上界。
- `render_handoff`：`context_pack={}` 且 `acceptance=""` ⇒ **逐字返回 `task`** ——
  beast / pet 现有交接行为不变。否则依次追加「原始目标 / 前置子任务结果 / 验收标准」。
- `stream_handoff`：渲染 prompt → `loop.astream(prompt, session_id=...)`；`deadline`
  非空且 >0 时用 `asyncio.timeout` 包住整个流。超时取消子流并抛
  `OrchestrationError(SUBTASK_TIMEOUT)`。
- `run_handoff`：同样渲染 prompt，经 `loop.arun(...)` 收口（保留 `DefaultLoop.arun` 的
  「等候后台收尾」语义；beast/pet 既有行为不变）；超时口径同上。

## D2 Router

```python
def _resolve(self, target: str) -> LoopPlugin   # 含 fallback 画像
async def handoff(self, target, handoff) -> LoopResult      # → run_handoff
def handoff_stream(self, target, handoff) -> AsyncIterator[LoopEvent]  # → stream_handoff
```

`_resolve` 在 `_agents` 未命中时回看 `_fallback`（`match()` 可能返回未登记的 fallback
画像，按 id 再次解析必须能命中，否则 general 子任务会假 `NO_AGENT_MATCH`）。
`deadline` 取自 `handoff.deadline`。

## D3 Scheduler

`_build_handoff(task_id, plan, subtask, *, session_id, attempt, previous_reason)`：

| 字段 | 来源 |
|---|---|
| `task` | `subtask.goal`（重试时追加有界失败提示） |
| `context_pack` | `build_context_pack(plan.goal, 依赖结果, max_tokens=DEFAULT_CONTEXT_TOKENS)` |
| `acceptance` | `subtask.acceptance` |
| `deadline` | `subtask_timeout > 0 ? float(subtask_timeout) : None` |
| `priority` | `subtask.priority`（调度排序已消费；此处随交接透传） |
| `session_id` | 发起方会话标识（空串 = 未归属） |

执行改为 `self._router.handoff_stream(profile.agent_id, handoff)`，其余
（`collect_result` + `subtask_progress` 白名单转译）逐字不变。`_handoff_goal` 删除。

**行为变更（有意）**：scheduler 路径的 prompt 由「子任务 goal + 前置结果字符串」变为
「task + 原始目标 + 前置结果 + 验收标准」—— 这是规格要求的字段消费，写入 ADR；beast/pet
空上下文路径逐字不变。

`subtask_timeout` 为构造注入（`float`，缺省 `0` = 关闭）。`<0` ⇒ 构造期
`OrchestrationError(INVALID_DISPATCH_POLICY, "非法子任务超时…")` —— 沿用既有「构造参数非法」
错误码，不新增第二码；配置层已在校验期阻断。

## D4 配置 `orchestration.subtask_timeout`

- `_DEFAULT_ORCHESTRATION_SUBTASK_TIMEOUT = 0`（0 = 不设限，缺省行为不变）。
- ConfigSpec：`--orchestration.subtask-timeout` / `CORE_ORCHESTRATION_SUBTASK_TIMEOUT`。
- `_orchestration_errors`：`_parse_int` 非 None 且 ≥0（bool 天然被 `_parse_int` 拒绝），
  否则 `非法子任务超时: orchestration.subtask_timeout=…（须为 ≥0 的整数，0=不设限）`。
- 访问器 `orchestration_subtask_timeout() -> int`。
- 组合根 `TaskScheduler(..., subtask_timeout=config.orchestration_subtask_timeout())`。
- `entry._key_to_patch` 顶层白名单加 `orchestration`，错误文案同步。

## D5 beast / pet

- beast：`try: result = await router.handoff(...) ... finally: session.recall()`；
  `last_result` / `last_trace_id` 仅在成功返回时写（失败时保持旧值）。
- pet `wake`：`asyncio.run(run_handoff(self._loop, TaskHandoff(task=prompt,
  session_id=self.session_id)))`。`render_handoff` 空上下文逐字返回 ⇒ prompt / 会话 ID /
  专属 loop / `source=pet` 全部不变。`run_handoff` 走 `arun` ⇒ 后台收尾仍被等候。

## D6 委托会话隔离

`core/loop/protocol.py`：

```python
current_session_id: ContextVar[str] = ContextVar("current_session_id", default="")
```

`DefaultLoop.astream` 在每次 `_act` 调用前后 `set` / `reset`（值取 `ctx.session_id`）。
`runtime._dispatch` 读取该值并 `profile.loop.arun(task, session_id=current_session_id.get())`
⇒ 委托产生的子 Agent 轨迹归入发起会话，而非全局未归属层。

- 只在 `_act` 周围设值（不是整个 `astream`）：避免影响推理/记忆等既有归属路径。
- `reset` 放 `finally`：工具异常不得把会话 ID 泄漏到后续调用。
- 三层命名空间仍由各自调用方填对：主任务 = 发起会话、beast = `beast.agent_id`、
  pet = 自身 UUID；`exclude_source_prefixes=("beast.","pet")` 逐字不动。

## D7 错误码

`OrchestrationErrorCode.SUBTASK_TIMEOUT = "SUBTASK_TIMEOUT"`。调度器侧由 0246 的
`_guarded_subtask` 捕获 → 子任务失败 → 重试 1 次 → 重拆 1 次 → `FAILED`（沿用既有恢复预算）。
