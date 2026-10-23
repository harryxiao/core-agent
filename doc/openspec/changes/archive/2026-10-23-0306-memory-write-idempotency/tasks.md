# Tasks — 0306 写入幂等重放

- [x] 1 红测试：`tests/test_memory_write_idempotency.py`（6 条）
- [x] 2 `MemoryStore.write` 幂等快路径 + 私有相等谓词
- [x] 3 文档：`memory.md` §5、`memory-interface.md` §1、ADR-0296、`known-risk.md` E242、
      `test-cases.md` §219
- [x] 4 门禁：`uv run pytest` / `ruff check` / `ruff format --check` / `pyright`
- [x] 5 反证 4 项（`cp` + `md5sum` 复原）
- [x] 6 `openspec validate --all`
- [ ] 7 归档 ⇒ 提交（须用户确认）
