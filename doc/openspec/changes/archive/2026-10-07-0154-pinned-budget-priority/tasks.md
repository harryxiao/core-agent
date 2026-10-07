# 0154 · 任务清单（常驻笔记预算 / 记忆三面路线图 G1）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`notes` **MODIFIED**「常驻（pinned）笔记（任务级硬约束锚）」
> （`pin_priority` + 优先级次序 + 整篇纳入 + 超限可见 + 4 Scenario）。
> 状态：**已归档**（2026-10-07；四门禁全绿，`openspec validate --all` 30/0）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/notes/spec.md`（delta，MODIFIED）：`pin_priority` / 优先级次序 / 整篇纳入 / 超限可见 + Scenario
- [x] 1.2 `openspec validate 0154-pinned-budget-priority` ⇒ valid
- [x] 1.3 ADR-0146（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_notes_pinned_budget.py`：`render`/`parse` `pin_priority` 往返；缺省省略、`abc` ⇒ 0
- [x] 2.2 同上：`pinned()` 次序 = 优先级降序 / 同优先级 `note_id` 升序
- [x] 2.3 同上：整篇纳入 —— 超预算篇**整篇**排除（其任何片段都不在块内）、其后各篇不入场
- [x] 2.4 同上：超限**留痕**（`warnings.warn`）+ `pinned_overflow()` 列出未进场 id；未超限 ⇒ 空 + 不告警
- [x] 2.5 同上：**单篇超限** ⇒ 整篇在场、块不空
- [x] 2.6 同上：`set_pinned(priority=...)` 往返 + `(pinned, priority)` 皆未变 ⇒ 不写盘；`unpin` 归零
- [x] 2.7 同上：`observe_turn` 保留 `pin_priority`
- [x] 2.8 `tests/test_notes.py`：`test_store_pinned_digest_is_deterministic_and_capped` 按新契约改写（整篇排除替代字符切片）
- [x] 2.9 CLI：`notes pin --priority` / `notes pinned`（在场 / 未进场）
- [x] 2.10 红态确认：实现前若干红 / 其余绿；实现后全绿

## 3. 实现

- [x] 3.1 `src/core/notes/models.py`：`NoteEntry.pin_priority` + `render_note` 可选行 + `parse_note` fail-closed
- [x] 3.2 `src/core/notes/store.py`：`pinned()` 优先级次序；`_assemble_pinned()`（整篇 + 前缀 + 首篇例外）；`pinned_digest()` 留痕；`pinned_overflow()`；`set_pinned(priority=...)`；`observe_turn` 保留
- [x] 3.3 `src/core/entry.py`：`notes pin --priority` + `notes pinned` + usage

## 4. 文档同步

- [x] 4.1 `doc/02-modules/notes.md` §3.4.1：优先级 / 整篇纳入 / 超限可见
- [x] 4.2 `doc/03-interfaces/notes-interface.md` §1/§3/§6：`pin_priority` + `pinned_overflow` + CLI
- [x] 4.3 `doc/04-testing/test-cases.md`：新增 `## 70.`（TC-PINBUDGET）
- [x] 4.4 `coding-plan/known-risk.md`：G1 行新增「已修」＋ §3 加 ADR-0146 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（含本 change 新增用例）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（notes）⇒ `shutil.move` 至 `archive/2026-10-07-0154-pinned-budget-priority/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（G1 → 已修）；ADR-0146 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(notes): 常驻预算显式优先级与整篇纳入，超限可见（change 0154）`
