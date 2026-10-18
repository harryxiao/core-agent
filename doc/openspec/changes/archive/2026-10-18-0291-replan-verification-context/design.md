# 设计 — 0291 任务级验收反馈闭环

## D1. 重拆输入：失败段前置且有界

**现状**（`scheduler._replan_input`）：`原始目标 → 已完成 → 失败项/死循环 → 通用尾句`，
且失败原因只在 `failure.failed` 非空时输出。任务级 `_Failure`（`PROGRESS_NOT_MET`）的
`failed=[]` ⇒ 原因与标准双双丢失。

**改法**：按失败类型精确分支。

```text
（任务级分支）
任务级验收未通过：{reason[:600]}
任务级成功标准（整体必须满足）：
- {criterion}
...
全部子任务已完成但整体未达标；请只补充能补齐上述差距的子任务，不要重复已完成的工作。
原始目标：{goal[:600]}
已完成子任务（不要重复安排）：
- {id}: {goal}
```

- `_MAX_REPLAN_GOAL_CHARS = 600`、`_MAX_REPLAN_CRITERIA_CHARS = 600`；reason 取既有
  `_MAX_EVENT_EXCERPT=600`。失败段在首位，2000 字符总截断后仍存活。
- **子任务失败 / 死循环分支**走原布局与原尾句（逐字不变）；任务级分支使用独立尾句
  「全部子任务已完成但整体未达标」，不得说「重新拆解尚未完成的部分」。
- 整体仍 `[:MAX_HANDOFF_CHARS]`。

## D2. 执行者看到任务级标准

`_task_criteria_text(plan)` 生成首行 `任务级成功标准（整体必须满足）：` + 每条标准，
整体截断到 600。`_build_handoff` 组合：

```python
criteria = self._task_criteria_text(plan)
if not criteria:
    acceptance = subtask.acceptance          # 逐字节与现状相同
else:
    budget = MAX_HANDOFF_CHARS - len(criteria) - 2
    acceptance = f"{subtask.acceptance[:budget]}\n\n{criteria}" if subtask.acceptance else criteria
```

- **不修改** `subtask.acceptance`：`SubtaskDecomposer.verify` 仍只按子任务自身标准判定，
  任务级标准只影响执行者输入（交接的 `[验收标准]` 已由 `render_handoff` 渲染）。
- 重试时同样附带（重试提示在 `task`，不占用 `acceptance`）。

## D3. 退化重拆回执 fail-fast

**判据**：`subtask.goal.strip() == replan_input.strip()`，精确相等，不做子串匹配。
LLM 失败回落会把 decomposer 输入原样作为 goal（`planner.py` 的兜底路径）。

**行为**：`decompose` 成功后、改写 `new_plan` 之前转 `FAILED`，
`SUBTASK_VERIFY_FAILED`，理由「重新拆解回执退化为拆解输入本身，未生成可执行子任务」，
`extra={"replans": plan.replans}`（此时计数已 +1），`return`。

**为何不「过滤后退化为空计划」**：部分过滤会让 `plan.order` / `plan.waves` 残留已删 id，
`_fan_out` 静默跳过 ⇒ 空波次、脏依赖、以死循环或无进展收场，而非预期的空计划失败。
fail-fast 更简单且语义一致。

**范围**：仅重拆；初次拆解的离线回落保持现状。

**被拒方案**：放松 `LLMTaskVerifier`（判定口径是产品契约，不能为一次冒烟放宽）；
只改 planner prompt（原因根本没进入重拆输入，prompt 无从得知）；增加重拆预算
（掩盖反馈缺失，且放大成本）；把任务级标准并入 `subtask.acceptance` 数据结构
（改变子任务验证语义）。

## 局限

- 原因与标准各 600 字符：超长标准尾部被截，判定器若依赖尾部条目需人工补充。
- 退化判据是**精确相等**：模型对输入做轻微改写（加标题/换行）不会被识别，仍会执行。
- 任务级标准追加到 `acceptance` 会占用子任务验收文本的预算（1900 字符 acceptance
  在 600 字符标准下被截到约 1398）。
- 重拆预算仍为 1：一次重拆仍不合格即终态失败。
