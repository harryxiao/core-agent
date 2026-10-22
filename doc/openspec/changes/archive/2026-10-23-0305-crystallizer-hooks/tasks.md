# Tasks — 0305 结晶 / 溶解钩子可用化

- [x] 1 红测试：`tests/test_memory_crystallizer.py`（复用门 / force / 溶解可写 / 引擎 artifact）
- [x] 2 `Crystallizer.crystallize` 复用门（`CRYSTALLIZE_MIN_REUSE = 3` + `force`）
- [x] 3 `Crystallizer.dissolve` 非空 `trace_id`
- [x] 4 `EvolutionOutcome.artifact` + `_crystallize_plugin` 保留产物（`force=True`）
- [x] 5 既有结晶用例按 `artifact` 增补断言（`tests/test_phase15.py`、`tests/test_evolution.py`）
- [x] 6 文档：`memory.md` §3.3、`memory-interface.md` §4、`evolution-interface.md`、
      ADR-0295、`known-risk.md` E241、`test-cases.md` §218
- [x] 7 门禁：`uv run pytest` / `ruff check` / `ruff format --check` / `pyright`
- [x] 8 反证 4 项（`cp` + `md5sum` 复原）
- [x] 9 `openspec validate --all`
- [ ] 10 归档 ⇒ 提交（须用户确认）
