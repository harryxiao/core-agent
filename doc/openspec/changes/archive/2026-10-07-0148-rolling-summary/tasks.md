# 0148 · 任务清单（记忆压实「增量滚动摘要」/ 账本 E90）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`memory` MODIFIED「记忆压实」（新增 Scenario「滚动合并既有摘要（不丢失）」）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/memory/spec.md`：MODIFIED「记忆压实」—— 追加滚动合并 SHALL 条文 + 新增 Scenario「滚动合并既有摘要（不丢失）」（既有 SHALL 段与 **6 条 Scenario 逐字保留**）
- [x] 1.2 `openspec validate 0148-rolling-summary` ⇒ valid；`validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）
- [x] 1.3 ADR-0140（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_memory.py::test_build_prompt_renders_existing_summary_slot`：含 `tags` 带 `summary` 的 semantic 条目 ⇒ prompt 含「现有摘要」槽与其原文；无该条目 ⇒ 不含该槽（实现前**红**）
- [x] 2.2 `tests/test_memory.py::test_compact_feeds_existing_summary_back_to_summarizer`：同会话二次压实 ⇒ 第二次摘要器输入**首元素**为既有摘要条目（实现前**红**）
- [x] 2.3 `tests/test_memory.py::test_compact_rolling_merge_preserves_prior_conclusions`：轮 1 摘要结论在轮 2 压实后**仍在**（实现前**红**）
- [x] 2.4 `tests/test_memory.py::test_compact_keeps_single_summary_entry_per_session`：同会话连续压实 ⇒ 摘要条目**恰一条**、`id` 不变
- [x] 2.5 红态确认：2.1 / 2.2 / 2.3 在实现前**失败**，实现后转绿；2.4 全程绿

## 3. 实现

- [x] 3.1 `src/core/memory/summarize.py`：新增 `_MAX_SUMMARY_CHARS = 2000`
- [x] 3.2 `summarize.py::build_prompt`：既有摘要条目（`"summary" in entry.tags`）渲染为「现有摘要」槽位；其余逐条 `- `；`Summarizer` 契约**不新增形参**
- [x] 3.3 `src/core/memory/store.py::_summarize_sessions`：投喂 `material = [prior, *entries] if prior else entries`
- [x] 3.4 关键：`_commit_summary` 第二参**仍只传本轮 `entries`**（既有摘要**不得被迁 L4**）
- [x] 3.5 不动项：`_below_gate` / `_score_importance` / `_commit_summary` 的 id·tags·trace / `_episodic_groups` / `read` / `write` / `migrate` / `forget` / `Summarizer` 别名 / `MemoryEntry` 字段

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/memory-interface.md`：§3 摘要契约补「材料含既有摘要条目」；§3 摘要式压实表 `id` 行改「滚动合并（内容融合、条目不增长）」；就地订正 §1 内**重复陈旧**的 `compact` 签名（line 46 旧版）
- [x] 4.2 `doc/02-modules/memory.md` §3.2.1：压实段补「滚动合并」一句
- [x] 4.3 `doc/04-testing/test-cases.md`：§64（TC-ROLLSUM，change 0148 / ADR-0140，账本 E90）
- [x] 4.4 `coding-plan/known-risk.md`：§1 `E90` 状态改「已修」＋就地注记；§3 加 ADR-0140 局限

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 基线 1734 + 本 change 新增 ⇒ 全绿
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical ⇒ `shutil.move` 至 `archive/2026-10-07-0148-rolling-summary/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E90 → 已修）；ADR 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(memory): 记忆压实增量滚动摘要（change 0148）`
