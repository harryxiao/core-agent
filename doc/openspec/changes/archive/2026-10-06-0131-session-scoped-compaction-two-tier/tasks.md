# 任务：压实按会话收窄 + 分档口径两档（change 0131 / E66 + E78）

## 1. 规格先行

- [x] `specs/memory/spec.md` delta：MODIFIED「记忆压实」（+ `session_id`）+ MODIFIED「温度分层检索」（三档→两档）
- [x] `openspec validate --all` 通过（31/0 → 归档后 30/0）

## 2. ADR

- [x] ADR-0124 + `## 变更追踪` 行

## 3. 测试先行（红）

- [x] `test_compact_scoped_to_session_leaves_others_intact`
- [x] `test_compact_scoped_session_scores_only_that_session`
- [x] `test_compact_default_session_id_keeps_full_store_semantics`
- [x] `test_compact_triggers_store_compaction`（fake 签名同步，断言 `spy.compacted == [("", session_id)]`）

## 4. 实现

- [x] `MemoryStore.compact(query="", budget=4096, *, session_id="")`
- [x] `_summarize_sessions(session_id="")` / `_episodic_groups(session_id="")`
- [x] `ui/api.py` `compact(session_id=session_id)`

## 5. 门禁

- [x] `.venv/bin/ruff check src tests` / `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` = 0/0/0
- [x] `.venv/bin/pytest -q`（1617 → 1620）

## 6. 文档与归档

- [x] `doc/03-interfaces/memory-interface.md` / `doc/02-modules/memory.md` / `doc/04-testing/test-cases.md`
- [x] 手工归档 `archive/2026-10-06-0131-session-scoped-compaction-two-tier/`
- [x] `coding-plan/phase-34.md` §1 E66 + §2 E78 + §9 行；`coding-plan/README.md` 索引
- [x] 记忆文件更新
- [x] 单次提交 `fix(memory): 压实按会话收窄 + 分档口径两档（change 0131）`
