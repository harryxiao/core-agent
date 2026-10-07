# 0150 · 任务清单（会话摘要提升 / 账本 E94）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`notes` **ADDED** Requirement「会话摘要提升（promotion）」；`memory` **MODIFIED**「记忆压实」（只读访问器条款）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/notes/spec.md`（delta，ADDED）：新 Requirement「会话摘要提升（promotion）」+ 6 Scenario
- [x] 1.2 `specs/memory/spec.md`（delta，MODIFIED）：「记忆压实」追加只读访问器 `summary_for` 条款 + 1 Scenario
- [x] 1.3 `openspec validate 0150-session-summary-promotion` ⇒ valid；`validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）
- [x] 1.4 ADR-0142（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_memory.py`：`summary_for` 返回摘要条目 / default 键 / 只读无副作用 / 无摘要器恒 None
- [x] 2.2 `tests/test_notes_promote.py`（新）：落盘 + 新实例读回 / 幂等单条 / id 确定性派生 / `--as` 覆盖 / tags 来源 / 空 slug 返回 None 不写盘
- [x] 2.3 `tests/test_notes_loop.py`：`test_loop_compaction_does_not_auto_promote`（设计裁决护栏）
- [x] 2.4 `tests/test_entry.py`：`promote` 跨进程 / 缺摘要非零退出 / 幂等 / `[pinned]` 标记 / usage 列表
- [x] 2.5 `tests/test_session_isolation.py`：提升 note 为全局层（跨会话 Consult 命中集相同）
- [x] 2.6 红态确认：新增用例实现前**失败**（`summary_for` AttributeError / `promote_session_summary` ImportError / `notes promote` 退出 1），既有全量绿

## 3. 实现

- [x] 3.1 `src/core/memory/store.py`：`summary_for(session_id)`（复用 `_existing_summary`，只读）
- [x] 3.2 `src/core/memory/protocol.py`：`MemoryStore` Protocol 加 `summary_for`
- [x] 3.3 `src/core/notes/promote.py`（新）：`promote_session_summary(...)`（id 派生 / 幂等覆盖 / 自动置常驻 / 复用 `update()`）＋ `__init__.py` 导出
- [x] 3.4 `src/core/entry.py`：`notes promote` 子命令 + `_notes_promote` + `_memory_summary` + 分发表 + `_NOTES_USAGE` + import 扩容
- [x] 3.5 `src/core/runtime.py`：**零改动**（确认无接线）

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/memory-interface.md`：方法表加 `summary_for`
- [x] 4.2 `doc/03-interfaces/notes-interface.md`：§3「提升」小节 + §6 CLI 行 + §5 loop 无改动
- [x] 4.3 `doc/02-modules/memory.md`：记忆压实小节补只读访问器
- [x] 4.4 `doc/02-modules/notes.md`：新增「会话摘要提升」小节 + §4 分工表 + §5 错误表
- [x] 4.5 `doc/04-testing/test-cases.md`：新增 `## 66.`（TC-PROMOTE）
- [x] 4.6 `coding-plan/known-risk.md`：§1 `E94` → 已修；§3 加 ADR-0142 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 基线 + 本 change 新增 ⇒ 全绿
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（notes + memory）⇒ `shutil.move` 至 `archive/2026-10-07-0150-session-summary-promotion/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E94 → 已修）；ADR 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(notes): 会话摘要提升为 canonical 常驻笔记（change 0150）`
