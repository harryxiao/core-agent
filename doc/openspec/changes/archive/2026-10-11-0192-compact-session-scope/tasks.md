# Tasks 0192 — 轮内压实会话化 + trace 会话键 + 诚实化

## 1. 规格（spec-first）

- [x] `specs/memory/spec.md`：MODIFIED「记忆压实」（归约范围口径：循环内一律会话化 + 显式调用才全量
      + 1 Scenario），既有 Scenario 标题零丢失
- [x] `specs/loop/spec.md`：MODIFIED「执行循环」（轮内压实的记忆固化步骤按本轮会话收窄
      + 1 Scenario），既有 39 Scenario 标题零丢失
- [x] `specs/context/spec.md`：MODIFIED「上下文自动压实」（产物 trace 携带会话键
      + 1 Scenario），既有 Scenario 标题零丢失
- [x] ADR-0182（`doc/01-architecture/adr.md`）

## 2. 测试先行（红）

- [x] `test_loop.py`：轮内压实的记忆固化**按本轮会话收窄**（他会话 L2 episodic 条目层级/内容不变，
      产物归本轮会话）；空会话轮行为逐字不变（全量聚合回归）
- [x] `test_loop.py`：轮内压实产物 `trace_id` 为 `compaction.<会话键>`（非常量 `"compaction"`）
- [x] `test_context_compaction.py`：`Compactor.persist` 的 `trace_id` 会话键化（空会话 ⇒
      `compaction.default`；非空 ⇒ `compaction.<sid>`）
- [x] `test_context_compaction.py`：docstring 诚实化文案（本轮消息 + 工具 I/O，不称「多轮历史」）

## 3. 实现（绿）

- [x] `loop/default.py`：`_compact` 的 `self._memory.compact()` → `compact(session_id=ctx.session_id)`
- [x] `loop/default.py`：`_compact` docstring 诚实化（本轮消息 + 工具 I/O；多轮历史由三层滑窗承载）
- [x] `context/compactor.py`：`persist` 的 `trace_id` 常量 → `f"compaction.{key}"`（两处）
- [x] `context/compactor.py`：`compact` docstring 诚实化 + provenance 死面**只注记不活化**
- [x] `memory/store.py`：`compact` 契约注（`:422-423`）改「供**显式调用**（CLI / 运维）」

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `openspec validate 2026-10-11-0192-compact-session-scope`
- [x] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E129（`known-risk.md` §1）+
      `doc/02-modules` / `doc/03-interfaces` 对应面
- [x] 单次提交 `feat(loop): …`
