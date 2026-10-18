# Change 0258 — 记忆压缩/压实硬化（P1）

> 编号说明：本 proposal/design 由 `/tmp/0255-memory-compaction-hardening.draft/` 还原，
> 正文逐字保留；原草稿编号 `0255` 已被 `2026-10-17-0255-skill-extraction-quality` 占用，
> 仓库内改用 `0258`。

## Why

记忆与自进化机制走查（2026-10-17，只读 review，`openspec validate --all` 32/32 绿）结论为
「机制完成、无阻塞缺口」，但存在若干非阻塞的结构性弱点，集中在三条链路：

1. **长任务下的摘要质量漂移**：`summarize.py` 的滚动合并无轮次/版本感知，同一会话反复
   compact 后早期结论被反复再压缩；`MAX_SUMMARY_CHARS=2000` + `_elide_summary` 尾部 800 字
   硬截断可能丢掉仍有效的早期决策上下文。
2. **compaction 的 token 预算口径不统一**：`loop/default.py::_should_compact`（步数阈值）与
   `context/budget.py::BudgetManager.enforce`（字符/预算）是两套独立估算，对「必留项」定义
   不一致，极端情况互相打架（一个说该压、一个说不能压）。
3. **checkpoint 非原子写**：`scheduler.py` 默认 `.core/scheduler-checkpoint.json` 单文件整写，
   进程写中途被 kill 产生半截 JSON，导致 resume 失败。

## What Changes

- **摘要分层保留**（`src/core/memory/summarize.py`、`src/core/memory/store.py`）：
  - 滚动合并 prompt 显式区分「结论区」与「事实区」，两区各自独立字符预算
    （新增 `SUMMARY_CONCLUSION_CHARS` / `SUMMARY_FACTS_CHARS`，合计仍受
    `MAX_SUMMARY_CHARS` 约束）；
  - `_elide_summary` 硬截断前优先按区分层 elide（保结论区全文，事实区尾部截断），
    仅当单区超限才整段截断。
- **预算口径统一**（`src/core/loop/default.py`、`src/core/context/budget.py`）：
  - `_should_compact` 只负责触发（步数阈值 + 「超预算」事实判定），预算裁决（哪些必留、
    压到多少）收敛到 `BudgetManager` 单一口径；
  - `_should_compact` 复用 `BudgetManager` 的预算估算结果，不再维护独立 token 估算。
- **checkpoint 原子写**（`src/core/orchestration/scheduler.py`）：
  - 默认 CheckpointFn 改为「写临时文件 + `os.replace` 原子替换」；
  - `load` 遇损坏 JSON 时降级为从头跑，并记 `checkpoint_corrupted` 遗留（可观测、非静默）。

## 影响面

- 规格：`memory` / `context` / `orchestration` 各 **ADDED/MODIFIED** 1 条聚焦 Requirement（含场景）。
- 代码：`src/core/memory/summarize.py`、`src/core/memory/store.py`、
  `src/core/loop/default.py`、`src/core/context/budget.py`、`src/core/orchestration/scheduler.py`。
- 测试：新增 `tests/test_memory_compaction_hardening.py`（分层 elide、预算口径一致、
  原子写与损坏降级，预计 5~6 例）。
- 缺省行为：正常路径产物与现状逐字一致；仅超限截断顺序、预算判定归属、checkpoint 落盘
  方式变化，均为纯硬化，无功能语义变更。

## 不做

- KeyFact 语义去重（embedding 合并）与 reject 教训 TTL 回收——归入后续「记忆质量打磨」
  change（低优先级，另行提案）。
- compaction/extraction 丢弃计数 metrics——同上，另行提案。
- 不新增 LLM 调用（分层 elide 为纯机械分层，不做 LLM 再压缩）。
- 不改 `_should_compact` 的步数阈值默认值与触发频率语义。
