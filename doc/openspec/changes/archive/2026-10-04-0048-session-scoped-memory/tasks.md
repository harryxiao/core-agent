# Tasks: 会话标识透传至记忆沉淀

## 1. 规格先行

- [x] 1.1 `specs/loop/spec.md` delta：MODIFIED「执行循环」——三入口接受会话标识，记忆沉淀写入 L2 条目 `session_id`；新增场景「记忆沉淀携带会话标识」
- [x] 1.2 `specs/memory/spec.md` delta：MODIFIED「分层记忆模型」——L2 写入记录会话归属；新增场景「写入记录会话归属」「未归属写入归缺省分组」
- [x] 1.3 `specs/ui/spec.md` delta：MODIFIED「三模统一内核启动」——标识由 API 层生成并透传、`compact` 真实压实、`get_memory` 按会话过滤；新增场景 3 条
- [x] 1.4 `openspec validate 0048-session-scoped-memory` 全绿

## 2. 测试先行（先红）

- [x] 2.1 `tests/test_loop.py`：`test_astream_memory_carries_session_id` —— 注入 SpyMemory，`astream("…", session_id="s-1")` 后断言沉淀条目 `session_id == "s-1"`；`test_astream_memory_session_defaults_empty` —— 不传时为空串（兼容）
- [x] 2.2 `tests/test_ui.py`：`test_run_loop_passes_session_id`（FakeLoop 记录 kwarg 实参）、`test_compact_calls_store_compact`（SpyMemory 记录 `compact` 实参 = 会话标识）、`test_get_memory_filters_by_session`（跨会话条目不可见）
- [x] 2.3 运行上述用例确认**失败**（红）

## 3. 实现

- [x] 3.1 `src/core/loop/protocol.py`：`run`/`arun`/`astream` 增 `*, session_id: str = ""`
- [x] 3.2 `src/core/loop/default.py`：三入口透传；`remember(trace_id, trajectory, *, session_id="")` 写入 `MemoryEntry.session_id`
- [x] 3.3 `src/core/memory/protocol.py`：`MemoryStore` 补 `compact(query="", budget=4096)` 声明
- [x] 3.4 `src/core/ui/api.py`：`run_loop` 透传 `session_id`；`compact` 直调 `self._memory.compact(session_id)`；`get_memory` 按 `entry.session_id` 过滤

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/loop-interface.md`：三入口签名补 `session_id`；`remember` 语义补会话归属
- [x] 4.2 `doc/03-interfaces/memory-interface.md`：`MemoryStore` 面补 `compact`；`session_id` 字段注释「写入侧归属」
- [x] 4.3 `doc/03-interfaces/ui-interface.md`：`compact` / `get_memory` 语义（真实压实 / 按会话读）

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src + tests）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（合并 delta 入 `doc/openspec/specs/*`、tasks 勾选、`mv` 入 `changes/archive/2026-10-04-0048-session-scoped-memory/`）
- [x] 5.5 `coding-plan/phase-19.md` §1 A2/E2 行标 ✅ 已关闭（change 0048 / commit）
