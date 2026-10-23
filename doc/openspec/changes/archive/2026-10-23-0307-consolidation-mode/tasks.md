# Tasks — 0307 巩固的可关闭性与水位语义

- [x] 1 红测试：`tests/test_memory_consolidation_mode.py`（7 类：off 零副作用 / 缺省不变 /
      off 不影响遗忘 / 配置三面 / 组合根接线 / 失败不推进水位 / 跨重启队列）
- [x] 2 `MemoryStore(consolidation_enabled=)` + `compact` 早返回
- [x] 3 配置：`memory.consolidation_mode` ConfigSpec + `consolidation_mode()` 访问器
- [x] 4 组合根接线：`runtime.build_runtime`
- [x] 5 文档：`memory.md` §3.21、`configuration-interface.md`、`memory-interface.md`、
      ADR-0297、`known-risk.md` E243、`test-cases.md` §220
- [x] 6 门禁：`uv run pytest` / `ruff check` / `ruff format --check` / `pyright`
- [x] 7 反证 5 项（`cp` + `md5sum` 复原）
- [x] 8 `openspec validate --all`
- [ ] 9 归档 ⇒ 提交（须用户确认）
