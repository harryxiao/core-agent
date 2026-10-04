# Tasks: 上下文按任务召回记忆

## 1. 规格先行

- [x] 1.1 `specs/context/spec.md` delta：MODIFIED「动态上下文构建」——检索依据由阶段改为任务，新增场景「按任务召回事实」
- [x] 1.2 `openspec validate 0038-task-keyed-memory-recall` 全绿

## 2. 测试先行（先红）

- [x] 2.1 `tests/test_context.py`：新增 `test_assembler_recalls_facts_by_task` —— 以 `MemoryStore` 写入与「任务」相关的事实，断言 `pack.facts` 命中该事实；且 query 为 task 而非 stage（用 spy/stub 记录 `read` 实参）
- [x] 2.2 `tests/test_loop.py`：新增 `test_perceive_does_not_retrieve_memory` —— 构造带 `MemoryStore` 的 loop，断言 `perceive` 不调用 `memory.read`（spy）且 `ctx.memory == []`

## 3. 实现

- [x] 3.1 `src/core/context/assembler.py`：`_gather_facts(self, query, budget)`；`build` 传 `task` 作 query
- [x] 3.2 `src/core/loop/default.py`：`perceive` 移除 `self._memory.read(...)` 与 `memory=` 实参

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/context-interface.md`：`build` docstring「按任务召回事实 + 阶段标注」；`stage` 注释「暂不参与选择」
- [x] 4.2 `doc/03-interfaces/loop-interface.md`：`perceive` 注释删「检索记忆」

## 5. 门禁

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → `openspec archive 0038-task-keyed-memory-recall`
