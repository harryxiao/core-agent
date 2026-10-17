# Design — 编排失败恢复（change 0246）

## D1 恢复回路

**现状**：`astream` 是「`for wave in plan.waves` + 末尾终态判定」的线性管道；任一失败分支
`RECOVERING` 后立即 `return`。`_enter_executing` 只认 `CREATED`/`SUSPENDED`。

**方案**：把计划执行与终态判定包进 `while True`：

```text
seed tracker/results
plan = plan or decompose(goal)
while True:
    emit plan_ready(replan=plan.replans)
    enter_executing()                      # CREATED/SUSPENDED/RECOVERING → EXECUTING
    failure = None
    for wave in plan.waves:
        outcomes_wave = fan_out(wave)
        if failed: outcomes_wave = retry_failed_once(outcomes_wave)
        outcomes = merge_by_id(outcomes, outcomes_wave)
        VERIFYING
        if still failed: failure = ...; break
        if stall: FAILED (DEADLOOP)
        checkpoint
        EXECUTING
    if failure is None:
        VERIFYING
        if success_met: DONE; break
        failure = PROGRESS_NOT_MET
    if plan.replans >= _MAX_REPLANS: FAILED; return
    RECOVERING
    plan.replans += 1
    checkpoint with new count             # 崩溃后续跑不重置预算
    plan = replan(...)                    # 空/异常 ⇒ FAILED
```

状态机无需新边：`VERIFYING→RECOVERING→EXECUTING` 已存在；`_enter_executing` 增加
`RECOVERING` 分支即可。

## D2 重试只重跑失败项

`_run_subtask` 新增关键字参数 `attempt`（缺省 1）与 `previous_reason`。重试批次只包含
本波失败 id，使用新信号量（同波次并发上限），重试 goal 追加有界提示：

```text
上一次尝试未通过验收：<reason ≤300 字符>
请换一种做法，确保满足验收标准：<acceptance>
```

`subtask_started` 的 payload 增 `attempt`；已完成子任务仍由 `_run_subtask` 幂等跳过。
合并 outcome 时按 `subtask_id` **替换**旧项（不追加重复失败记录）。

## D3 重新拆解

**输入**：原 goal + 已完成子任务摘要（id/goal）+ 失败子任务与原因，均按既有
`_MAX_HANDOFF_CHARS` 上界截断。

**新计划**：
- `goal` / `success_criteria` 保留原值（原标准非空时**不采纳**新生成标准，防成功标准漂移）；
  原标准为空且 planner 新生成标准时采纳；
- `replans = 旧值 + 1`；
- **清空**本任务 tracker 完成集、`_results` 与累计 `outcomes` —— 新 DAG 可能复用 id 但语义
  不同，保留会误跳过或注入脏依赖。旧计划的结果仍留在历史检查点中。

**预算**：`_MAX_REPLANS = 1`。重拆前 `plan.replans += 1` 并立即写检查点，确保崩溃续跑
不会把预算重置为 0。重试次数 `_MAX_SUBTASK_RETRIES = 1` 是进程内计数（不跨进程持久化）。

**失败**：`decompose` 抛错、空计划或预算耗尽 ⇒ `transition(FAILED)` + `task_failed`；
`code` 取最后一次失败原因（`SUBTASK_VERIFY_FAILED` / `SUBTASK_EXECUTION_FAILED` /
`PROGRESS_NOT_MET`），payload 增 `attempts` / `replans`。

## D4 异常归一化

`_fan_out` 对每个 `_run_subtask` 包一层 guard：

- `OrchestrationError` ⇒ `SubtaskOutcome(ok=False, error=exc.code, reason=str(exc))`；
- `Exception` ⇒ `SUBTASK_EXECUTION_FAILED`（`type(exc).__name__: str(exc)`，有界）；
- `CancelledError` 不捕获（外部取消语义不变）。

guard 负责补发 `subtask_completed(ok=False)`，保证事件配对。异常由此进入 D1 的重试/重拆，
不再穿透调度器。

## D5 空计划守卫

`plan.subtasks` 为空时，现有代码会跳过所有波次并把空标准判为通过 ⇒ 假 `DONE`（P0-6）。
在首次执行与每次重拆后统一校验：空计划 ⇒ `task_failed(SUBTASK_VERIFY_FAILED,
"计划为空，无法执行")`。

## D6 检查点

`Plan.replans: int = 0`；`plan_to_dict` 写 `"replans"`，`plan_from_dict` 缺键回落 0。
`CheckpointFn` 4 参签名不变，`entry.py` 的 `plan_from_dict` 续跑自动带回计数。

## 局限

- 重试只覆盖「验收/执行失败」；消费方断流、运行中 `cancel()`、`on_done` 异常逃逸仍属 D1。
- 重拆后重跑新计划可能重复已完成的副作用（只清空完成集，不重放旧结果）；这是正确性优先。
- 任务级判定误判可能触发一次不必要的重拆（0248 的判定器 fail-closed 只触发一次恢复）。
- 重试 attempt 不跨进程持久化：崩溃续跑会重新获得 1 次重试（有界）。
