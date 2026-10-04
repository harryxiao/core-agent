# Tasks: 记忆摘要式压实

## 1. 规格先行

- [x] 1.1 `specs/memory/spec.md` delta：MODIFIED「记忆压实」（摘要提炼 + 会话聚合 + L4 归档
      可逆 + 无摘要器降级 + 可撤销场景）
- [x] 1.2 `specs/context/spec.md` delta：MODIFIED「上下文自动压实」（沉淀产物为 semantic
      条目 + 标注原始 id 出处 + 明确启发式降级路径）
- [x] 1.3 `openspec validate 0041-memory-summary-compaction` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/memory-interface.md`：`MemoryStore` 增 `summarizer` 注入点；
      `compact` 语义（会话聚合 → semantic 摘要条目 + 原条目迁 L4）；摘要条目字段约定
      （`kind="semantic"`/`source="compaction"`/`trace_id=f"compaction.{session_id}"`/
      `tags` 携带 `from:<id>`）；`migrate` 记可逆效应
- [x] 2.2 `03-interfaces/context-interface.md` §4：`persist` 产物为 semantic 条目 + 出处
- [x] 2.3 `01-architecture/adr.md`：ADR-0046（摘要接缝 + 压实可逆 + 触发接线）

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_memory.py`：注入假摘要器 → `compact` 产出 semantic 摘要条目
      （tags 含原 id）、原条目迁 L4、L2 不再检出原条目
- [x] 3.2 `tests/test_memory.py`：未注入摘要器 → 不写摘要、原条目不动（降级）
- [x] 3.3 `tests/test_memory.py`：`migrate` 记效应；`rollback(trace_id)` 后原条目迁回、
      摘要条目移除（可逆）
- [x] 3.4 `tests/test_context.py`：`persist` 产物 `kind="semantic"` 且 `tags` 带原始 id
- [x] 3.5 `tests/test_loop.py`：token 预算超限/`should_compact` 为真时触发压实
      （假 compactor 记录调用）；未注入 compactor 时行为不变
- [x] 3.6 `tests/test_phase13.py`：runtime 注入 `context.Compactor` 与 `Summarizer`
      （假 provider 不触网）

## 4. 实现

- [x] 4.1 `src/core/memory/summarize.py`（新）：`Summarizer` 类型 + `build_prompt` +
      `summarize_with` 适配器；`memory/__init__.py` 导出
- [x] 4.2 `src/core/memory/store.py`：`summarizer` 注入点 + `compact` 升级（会话聚合 →
      摘要 → 写 semantic 条目 → 原条目迁 L4）；`migrate` 记 `EffectTracker`
- [x] 4.3 `src/core/context/compactor.py`：`persist` 产物 semantic + 出处
- [x] 4.4 `src/core/loop/default.py`：注入 `compactor`；`should_compact`/预算超限触发
      压实 → persist → `memory.compact`
- [x] 4.5 `src/core/runtime.py`：构造 `context.Compactor(memory=memory)` 与
      `Summarizer`（包主 LLM）并注入 loop / memory

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（delta 合并进 specs/ + mv 到 archive/）
