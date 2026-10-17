# Design — 目标监控（change 0248）

## D1 拆解产物携带成功标准

```python
@dataclass
class DecomposeResult:
    subtasks: list[Subtask]
    success_criteria: list[str] = field(default_factory=list[str])
```

`Planner = Callable[[str], list[Subtask] | DecomposeResult | Awaitable[...]]` ——
`decompose` 用 `isinstance(produced, DecomposeResult)` 分流；返回 list 的既有桩不改。
`SubtaskDecomposer` 的离线默认（无 planner）与 `LLMSubtaskPlanner._fallback` 均不带标准。

成功标准优先级：**显式非空 > planner 生成 > 空**。重拆路径由 0246 既有逻辑
（原标准非空则覆盖新计划）保持，本 change 不改。

## D2 拆解 prompt 与解析

`_DECOMPOSE_SYSTEM` 顶层改为 `{"success_criteria": [...], "subtasks": [...]}`，插入规则：
「success_criteria 是整体目标的成功标准：2-5 条、每条可客观判定真伪、覆盖整体目标，
不要复述子任务的 acceptance」。

`_parse` → `DecomposeResult`：

- 标准：仅收**字符串**、`strip()` 后非空、保序去重、至多 `_MAX_SUCCESS_CRITERIA = 5` 条。
- 子任务：`depends_on` 每项先 `strip()` 再判已声明 id（修：`" 1 "` 现被静默丢弃）；
  重复 id **保留首个**（修：重复 id 使拓扑序不完整，现被误报 `DEADLOOP_DETECTED`）。
- `_fallback` 返回单子任务 + **空标准**：planner 失败时若仍带标准，同源 LLM 判定
  fail-closed 会把本可执行的任务拖死（与 0246「失败可恢复、不误判」同向）。

## D3 任务级判定器

```python
class LLMTaskVerifier:
    async def __call__(
        self, goal: str, criteria: list[str], outcomes: list[SubtaskOutcome]
    ) -> VerifyResult
```

- **复用** `_VERIFY_SYSTEM`（判定协议不变，镜像零新增）：`_judge` / `_fail_closed` 提为
  模块级私有函数，`LLMVerifier` 与 `LLMTaskVerifier` 共用；单次重试、fail-closed 同口径。
- 输入渲染：Goal / 成功标准逐条 / 子任务结果（`ok` + 失败原因 + 结果节选
  `_TASK_VERIFY_MAX_REPLY = 500` 字符），整体 `redact_secrets` 脱敏后截断到
  `_MAX_VERIFY_CHARS`（4000）—— 提示词里不出现密钥形态子串。
- `criteria` 为空时直接通过（不调模型；空标准后向兼容分支由调度器先行短路）。

## D4 调度器接线

```python
SuccessChecker = Callable[
    [str, list[str], list[SubtaskOutcome]], VerifyResult | Awaitable[VerifyResult]
]
```

`_success_met(task_id, goal, plan, outcomes) -> VerifyResult`（async）：

- 空标准 ⇒ `VerifyResult(passed=True)`（不调 checker，既有行为）。
- checker 同步/异步结果归一（`inspect.isawaitable`）。
- **异常 / 非法返回 fail-closed**：返回 `passed=False` 并 trace（不抛裸异常、不静默放行）；
  `CancelledError` 属 `BaseException`，照常透传。
- 未达标 ⇒ 以 `PROGRESS_NOT_MET` 构造 `_Failure`（原因取判定器理由），复用 0246 的
  重拆 1 次 / 耗尽 `FAILED` 回路；重拆后再次判定。
- 缺失 checker 的 fail-fast（`MISSING_SUCCESS_CHECKER`）逐字保留。

## D5 ProgressTracker 三态

- `start(task_id, id)`：计入 `started`（distinct 子任务），清除该 id 的 `failed`（重试开始）。
- `fail(task_id, id)`：计入 `failed`（当前未恢复的失败项）。
- `record(task_id, id)`：计入 `completed`，清除 `failed`（重试成功）。
- `progress(task_id) -> {"started": n, "completed": n, "failed": n}`。
- `reset` 清空三态；`detect_stall` 仍只用 completed 签名（死循环判据不变）。

调度器 choke point：`_run_subtask` 在幂等跳过之后、派发之前 `start`；`_guarded_subtask`
在结果 `ok=False`（含无匹配 / 验收失败 / 异常归一）时 `fail`。成功路径由既有 `record` 清除。

## D6 组合根

`runtime.py` 注入 `success_checker=LLMTaskVerifier(llm, model=app.llm.model)`。与 D2 标准
生成同 change 落地：若只生成标准不注入 checker，所有生产任务会以
`MISSING_SUCCESS_CHECKER` 失败（本 change 的 P0 前置）。
