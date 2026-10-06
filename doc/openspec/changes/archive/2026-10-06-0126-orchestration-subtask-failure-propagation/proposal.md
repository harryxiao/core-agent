# 提案 — 子任务失败态传播（假成功收口）（change 0126 / phase-34 E63）

## 背景

`coding-plan/phase-34.md`（全系统架构走查缺陷账本）登记的真缺陷 **E63**（**最高危**）：编排器
`_run_subtask` **只认验收门结论**，**丢弃子 Agent 循环的失败态** ⇒ 子任务**假成功**。

| # | 一手事实（2026-10-06 复核，行号已核实） | 后果 |
|---|---|---|
| 1 | `scheduler.py:440-443` `result = await collect_result(...)` → `verify = await self._decomposer.verify(subtask, result.reply)` | `result.failed`（循环未达成 / 异常终止 / 预算耗尽）**从未被读** |
| 2 | `scheduler.py:455/462` `ok: verify.passed` / `if verify.passed:` | 推进判据**只看验收门**；无验收标准时退化为「回复非空即通过」⇒ 失败态 + 非空回复 = **假成功** |
| 3 | `runtime.py:797`（`_dispatch` 正解）`return {"ok": not result.failed, "reply": result.reply}` | 对照正解：`delegate` 路径**已**把 `failed` 并入 `ok`，编排路径**漏了同一条** |
| 4 | `loop/protocol.py:24` `LoopResult.failed: bool`（注释「目标未达成/异常终止/预算耗尽为 True」） | 失败信号**语义明确、已在终态**，只是编排层不消费 |

**契约面现状**：`orchestration/spec.md` 「子任务验收门」`Requirement` 只规定「验收不通过 ⇒ 失败不推进」，
**未**规定「执行失败 ⇒ 失败不推进」⇒ 假成功在规格上是**空白**（非违约口径）。按本仓 SDD 惯例
**规格先行**（非 `skip_specs`）。

## 变更目标

**`orchestration/spec.md` 「子任务验收门」Requirement MODIFIED**（补一条 fail-closed 口径 + 1 个 Scenario）：

1. **执行失败态 fail-closed** —— 子任务执行单元返回失败态（循环未达成 / 异常终止 / 预算耗尽）时，
   验收门 SHALL 判**不通过**，SHALL NOT 因合成回复非空而通过。
2. **失败态传播** —— 该失败态 SHALL 传播至子任务终态（`ok = 验收通过 且 执行未失败`）与 fan-in
   推进判据（与 `runtime.py:797` 的 `delegate` 正解同口径）。

## Non-goals

- **不改验收门本义**：LLM 对照判定 / 离线非空降级 / 判定器不可用 fail-closed **逐字不变**（本 change 只
  **加**「执行失败」这一前置收窄）。
- **不改 `subtask_completed` / `task_failed` 载荷形状**（下游消费面已依赖）。
- **不改状态机 / 波次 / fan-in 结构**（`_failed` 收口与 `RECOVERING` 转移复用既有路径）。
- **不动 `loop` 层**（`LoopResult.failed` 语义与产出已正确）。
- **不动 `delegate` 路径**（`runtime.py:797` 已正确，本 change 只是让编排路径**对齐**它）。

## 判据与取舍

**执行失败的结构化错误码取 `SUBTASK_EXECUTION_FAILED`（新增枚举成员），不复用 `SUBTASK_VERIFY_FAILED`。**
理由：假成功的**根因**是「执行失败被误当验收通过」——若仍以「校验失败」命名，日志/trace 会把
「循环未达成」读成「验收标准未达」，掩盖真因。新增枚举成员为**纯追加**（不破坏既有 `task_failed`
波级收口：波级仍按既有 `SUBTASK_VERIFY_FAILED` 汇总失败子任务列表，与「哪一条执行失败」正交）。

**失败理由取循环终态**：`result.failed` 为真而验收门本会通过时，理由记为「子任务执行未达成」；
`verify.reason` 在验收本就失败时**照旧**保留（两条失败因由不互相覆盖）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 误伤「回复非空但 `failed=True`」的正当场景 | `failed` 语义即「目标未达成」（`loop_failed` / 预算耗尽 / 轮数上限）⇒ 本就**不应**推进；离线判定退化的前提是**执行成功** |
| 新增错误码扰动下游 | 纯追加枚举成员；波级 `task_failed` 收口码不变；`subtask_completed.ok` 由 `verify.passed` **真值** |
| 改动热路径（`_run_subtask`） | 判据合并为单行真值 `verify.passed and not result.failed`，语义可读；回归由既有编排用例守门 |

## 兼容性

- `subtask_started` / `task_failed` / `task_finished` 载荷**零变更**。
- `subtask_completed` 的 `ok` 字段**取值域不变**（仍 `bool`），仅在「执行失败 + 验收本会过」这一
  此前**错误**的组合上由 `true` 纠正为 `false`（**这正是本 change 的目的**）。
- `TaskScheduler.run` 的抛出语义不变（假成功纠正为 `SUBTASK_VERIFY_FAILED` 波级收口后 `run` 抛错）。
