# 裁决：否决（2026-10-18）

> 原草稿编号 `0255`，因该号已被 `2026-10-17-0255-skill-extraction-quality` 占用，仓库内改用 `0258`。
> 本目录为**否决记录**：proposal / design / tasks / spec delta 均未实施，delta **未**并入 canonical
> specs；已移至 `doc/openspec/rejected-changes/`，不参与 `openspec validate --all`。

## 结论

原稿三项主诉均不建议实施：两项前提已被现行代码/规格覆盖或推翻，一项已在更上游完成。

## 逐项裁决

### D1 摘要分层（结论区 / 事实区）——否决

- **前提过时**：草稿称「尾部 800 字硬截断可能丢掉仍有效的早期决策」。现行
  `src/core/memory/summarize.py:47` 的 `_elide_summary` 已是**首尾保留**（首部约 1200 + 尾部 800，
  change `0193`），memory 规格亦明文规定该口径。早期结论位于首部，不在被截断区间。
- **已被上游兜底**：`src/core/runtime.py:602-613` 注入 `summary_promoter`，会话摘要**首次越过**
  上界时把**完整摘要**交付 canonical 真相层（`promote_session_summary`，只交付一次）；后续滚动
  合并无法销毁已提升的早期结论。
- **方向相反**：草稿的 800/1200 分层把首部预算从约 1200 降到 800，反而缩减早期结论的保留空间。
- **格式冲突**：现有 merge prompt 已是「结论 / 决策 / 未决事项」三段式；再叠
  `<conclusions>/<facts>` 哨兵与三段式冲突，且依赖模型稳定输出标记，收益不明确。
- 唯一有潜在价值的是 `[rN]` 轮次锚点，但无实际漂移证据，且需同步 prompt pin/mirror，暂不做。

### D2 预算口径统一到 BudgetManager——否决

- **「两套独立估算」不成立**：loop 的 `ctx.token_used` 经 `core.context` 再导出使用
  `core.tokens.estimate_tokens`（`src/core/loop/default.py:31`），`BudgetManager` 缺省使用同一
  `core.tokens` 估计器（`src/core/context/budget.py:11`）；change `0230` 才允许注入不同估算器。
- **作用对象不同**：`BudgetManager.enforce` 裁 `ContextPack`（装配后的提示词区块）；压实触发判
  `LoopContext`（`rounds` + 历史/消息/分层摘要）。二者不是同一对象的两种口径。
- **职责错位**：把 `rounds` 触发判据搬进 ContextPack 层会把 loop 状态带入 context 层；design 的
  `should_compact(transcript_chars, turn_count)` 与 proposal「复用预算估算」自相矛盾，并退回
  字符计量、绕开可注入的 token 估算器。
- 现行 context 规格已明确触发判据（`loop.compact_steps` 或 token 预算，每轮至多一次），
  `Compactor.should_compact` 已实现，无「互相打架」证据。

### D3 checkpoint 原子写——已完成（否决）

- `FileCheckpoint`（`src/core/orchestration/scheduler.py:45-82`）在 change `0230` / G7 已实现同目录
  临时文件 + `os.replace` 原子写；orchestration 规格「文件型检查点实现」亦明文要求原子写。
- 该实现**仅测试使用**（`tests/test_orchestration.py:917`）；生产组合根注入的是
  `CheckpointStore`（`src/core/durability/store.py`，`~/.core/state/checkpoints.jsonl`），其
  `_persist` 同为原子写。草稿指错了组件。
- 唯一残留缺口：`CheckpointStore._load` 对损坏行 `continue` **静默跳过**，无留痕。属独立的小
  可观测性项，价值取决于是否实际遇到「任务莫名从头跑」，不在本 change 范围。

## 残留候选（另立 change 时才考虑）

1. `CheckpointStore._load` 损坏行 `warnings.warn`（只报行号，不回显正文）——最小、最安全。
2. compaction 事件补 `dropped` 计数——诊断「记忆是否在悄悄变少」价值更高，但属新小 change。

## 草稿「不做」清单复核

- KeyFact 语义去重：大部分已被 `memory` 规格「关键事实的跨压实合并」覆盖（同实体 slug 覆盖
  更新、保留首见时间戳），剩余近义表述合并价值有限。
- reject 教训 TTL：与 change `0251` 的 L2 软上限 + 遗忘机制重叠。
- 丢弃计数 metrics：见上「残留候选 2」。
