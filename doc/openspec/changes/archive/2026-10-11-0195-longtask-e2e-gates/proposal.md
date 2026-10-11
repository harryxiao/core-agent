# Proposal 0195 — 长任务端到端门禁（测试，规格中性）

## Why（缺口）

批次 `Phase 36` 前五条（`0190`~`0194`）各自修了长任务链路的一环，但**没有任何端到端锚**
把「产出 → 注入」两端接起来 —— 这是本批次评估里点名的**结构缺口**：

- **压实 → 注入两端分离**：`tests/test_loop.py` 的压实用例只断言**记忆态**（`compaction.summary.s1`
  存在）；`tests/test_history_replay.py` 的摘要注入用例**手播**摘要条目。二者之间
  「**上一轮压实的产物真的进了下一轮推理的 system prompt**」**无用例断言**。
- **越界与解耦只测到上下文对象**：`0193`（首尾保留）只在 `_elide_summary` / `build_prompt`
  单元层断言；`0194`（解耦）只在 `ctx.summary_long` 对象层断言。**装配后**的形态无锚。

⇒ 回归时「哪一环断了」无法从端到端视角发觉。

## What Changes

**零 `src/` 改动**，新增 `tests/test_longtask_e2e.py`（3 个端到端用例）+ ADR-0185。

**规格中性判定**：本 change **不改任何行为**，只补测试锚 ⇒ 无 spec delta，
`.openspec.yaml` `skip_specs: true`（沿 `0156` / `0189` 先例）。

**防过空断言**（每条都验证「非任意通过」）：
- ① 断言注入内容是**上一轮压实产物**（`上一轮：季度结论 已完成` 字串），非泛化「有摘要」；
- ③ 断言尾部**锚点字串** `最新结论：尾部保真锚点XYZ` **与**中略标记 `⋯（中略`；
- ④ 断言历史原文**不回灌**（`messages[1:] == ["新一轮"]`）。

**反证（门禁非空过的证明）**：逐条**临时回退**其目标行为并确认对应用例转红 ——
① 禁用 `_compact` 的 `memory.compact` ⇒ ①转红；③ 改回纯头截断 ⇒ ③转红；
④ 恢复 `_load_summaries` 的 `history_turns <= 0` 闸 ⇒ ④转红；三者复原后全绿。

## Impact

- **代码**：**零 `src/` 改动**（`git diff --stat src/` 为空）。
- **测试**：+3（`tests/test_longtask_e2e.py`）。
- **不做**：**不重复** CLI `--resume` 会话端到端（已由 `test_entry.py::test_task_resume_reuses_checkpoint_session`，
  change `0190`，承载）；不引入新依赖、不触网（假摘要器 + 桩 provider）。
