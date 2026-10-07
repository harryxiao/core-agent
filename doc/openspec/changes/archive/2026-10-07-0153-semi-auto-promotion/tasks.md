# 0153 · 任务清单（半自动提升 / 记忆三面路线图 G3）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`memory` **MODIFIED**「记忆压实」（上界可见性 + 提升钩子 + 3 Scenario）；
> `notes` **MODIFIED**「会话摘要提升（promotion）」（触发面扩 + pin 分路径 + 2 Scenario + 1 收窄）。
> 状态：**已归档**（2026-10-07）；四门禁全绿；`openspec validate --all` 归档前 31/0 ⇒ 归档后 30/0。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/memory/spec.md`（delta，MODIFIED）：「记忆压实」+ 上界可见性 / 提升钩子条款 + 3 Scenario
- [x] 1.2 `specs/notes/spec.md`（delta，MODIFIED)：「会话摘要提升」触发面扩 + `pin` 分路径 + Scenario
- [x] 1.3 `openspec validate 0153-semi-auto-promotion` ⇒ valid；`validate --all` ⇒ 归档前 31/0 ⇒ 归档后 30/0
- [x] 1.4 ADR-0145（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_memory_summary_promotion.py`：摘要**首次越界** ⇒ 钩子**恰一次**（收到 `(session_id, 摘要条目)`）
- [x] 2.2 同上：**已越界**再次压实 ⇒ 钩子**不再**被调用（一次语义）
- [x] 2.3 同上：摘要**未越界** ⇒ 钩子从不被调用（边界护栏，零回归）
- [x] 2.4 同上：钩子 UNWIRED ⇒ 不交付、摘要照写（零回归）
- [x] 2.5 同上：钩子**抛错** ⇒ 降级（`warnings.warn`）+ 摘要照写 + 原条目照迁 L4
- [x] 2.6 同上：`session_id` 为空串 ⇒ 不交付
- [x] 2.7 同上：端到端（MemoryStore + NoteStore + 真实闭包）⇒ canonical 落盘、`pinned is False`、幂等单条
- [x] 2.8 `tests/test_notes_loop.py`：护栏用例改写为「**未越界** ⇒ 不提升（钩子不触发 + 无 `session-*.md`）」
- [x] 2.9 `tests/test_notes_promote.py`：补 `pin=False` ⇒ 产出**不**置常驻
- [x] 2.10 红态确认：实现前若干红 / 护栏绿；实现后全绿（基线以开工实测为准）

## 3. 实现

- [x] 3.1 `src/core/memory/summarize.py`：`_MAX_SUMMARY_CHARS` → 公开 `MAX_SUMMARY_CHARS`；新增 `SummaryPromoter` 契约
- [x] 3.2 `src/core/memory/__init__.py`：导出 `MAX_SUMMARY_CHARS` / `SummaryPromoter`
- [x] 3.3 `src/core/memory/store.py`：`__init__(..., summary_promoter=None)`；`_summarize_sessions` 于 `_commit_summary` 后调 `_deliver_promotion`（越界一次 + 空串跳过 + 抛错降级）
- [x] 3.4 `src/core/notes/promote.py`：新增 `pin: bool = True` 形参 → `NoteEntry(pinned=pin)`
- [x] 3.5 `src/core/runtime.py`：`NoteStore` 构造上移 + `import promote_session_summary` + 注入 `_promote_summary`（`pin=False`）

## 4. 文档同步

- [x] 4.1 `doc/02-modules/memory.md`：压实节补上界可见性 + 提升钩子
- [x] 4.2 `doc/02-modules/notes.md` / `doc/03-interfaces/notes-interface.md`：提升节补半自动路径 + `pin`
- [x] 4.3 `doc/03-interfaces/memory-interface.md`：`MemoryStore` 构造面补 `summary_promoter`
- [x] 4.4 `doc/04-testing/test-cases.md`：新增 `## 69.`（TC-SEMIAUTO）
- [x] 4.5 `coding-plan/known-risk.md`：G3 行新增「已修」＋ §3 加 ADR-0145 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（含本 change 新增用例）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（memory + notes）⇒ `shutil.move` 至 `archive/2026-10-07-0153-semi-auto-promotion/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（G3 → 已修）；ADR-0145 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(notes): 摘要首次越界半自动提升，落 canonical 不自动 pin（change 0153）`
