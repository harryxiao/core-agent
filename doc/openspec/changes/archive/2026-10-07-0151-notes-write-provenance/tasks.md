# 0151 · 任务清单（笔记写入来源守护 / 账本 E95）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`notes` **MODIFIED**「Consult → Build → Update 循环纪律」（来源守护条款）＋
> **MODIFIED**「会话摘要提升（promotion）」（撞车拒绝条款）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/notes/spec.md`（delta，MODIFIED）：「Consult → Build → Update 循环纪律」+ 来源守护条款 + Scenario
- [x] 1.2 `specs/notes/spec.md`（delta，MODIFIED）：「会话摘要提升（promotion）」+ 撞车拒绝条款 + Scenario
- [x] 1.3 `openspec validate 0151-notes-write-provenance` ⇒ valid；`validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）
- [x] 1.4 ADR-0143（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_notes.py`：`observe_turn` 撞 `source != "notes.turn"`（人工笔记）⇒ 该篇**正文与标题逐字不变**、沉淀落派生主题 `<topic>-2`
- [x] 2.2 `tests/test_notes.py`：`observe_turn` 撞**自己**来源（`notes.turn`）⇒ 仍**覆盖同一**主题（既有行为逐字不变，防回归）
- [x] 2.3 `tests/test_notes.py`：撞 `source != "notes.turn"` 的**常驻**笔记 ⇒ 常驻笔记正文/标题逐字不变、`pinned` 保留，沉淀落派生主题
- [x] 2.4 `tests/test_notes_promote.py`：`promote` 撞非 promotion 来源且未给 `--as` ⇒ 返回 `None` + **不写盘**
- [x] 2.5 `tests/test_notes_promote.py`：`promote` 撞非 promotion 来源但**给了** `--as` ⇒ 照常覆写
- [x] 2.6 `tests/test_entry.py`：`notes promote` 撞非 promotion 来源（不给 `--as`）⇒ 退出码非零、`*.md` 逐字不变
- [x] 2.7 红态确认：新增用例实现前**失败**，既有全量绿（基线 1793）

## 3. 实现

- [x] 3.1 `src/core/notes/store.py`：`_TURN_SOURCE` 常量 + `observe_turn` 来源守护 + `_derived_turn_topic` 辅助
- [x] 3.2 `src/core/notes/promote.py`：`promote_session_summary` 撞非 `notes.promote` 来源且未给 `as_note_id` ⇒ 返回 `None`（不写盘）
- [x] 3.3 `src/core/entry.py`：`_notes_promote` 的 `None` 分支文案覆盖「撞车拒绝」（不新增错误码）
- [x] 3.4 `src/core/runtime.py`：**零改动**（钩子签名不变）

## 4. 文档同步

- [x] 4.1 `doc/02-modules/notes.md`：§3.5 写回 + §3.5.1 提升 各补来源守护
- [x] 4.2 `doc/03-interfaces/notes-interface.md`：写回 / 提升 接口面补来源守护
- [x] 4.3 `doc/04-testing/test-cases.md`：新增 `## 67.`（TC-WRITESAFE）
- [x] 4.4 `coding-plan/known-risk.md`：§1 加 `E95`（已修）；§3 加 ADR-0143 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 基线 + 本 change 新增 ⇒ 全绿
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（notes）⇒ `shutil.move` 至 `archive/2026-10-07-0151-notes-write-provenance/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E95 → 已修）；ADR 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`fix(notes): 写入来源守护，杜绝跨来源误覆写（change 0151）`
