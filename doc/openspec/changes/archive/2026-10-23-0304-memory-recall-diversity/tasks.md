# Tasks — 0304 召回多样性与注入统计

## 1. 规格与测试先行

- [x] 1.1 `specs/memory/spec.md` ADDED ×1（召回的多样性控制与注入统计）
- [x] 1.2 新增 `tests/test_memory_recall_diversity.py`（会话上限 / 全局豁免 / 近重复 / 空正文 /
      统计不变式 / minimum_budget / read 兼容）
- [x] 1.3 红/绿分布记录（实现前新用例红）

## 2. 实现

- [x] 2.1 `protocol.py`：`RecallResult` + `MemoryStore.recall()` 协议
- [x] 2.2 `store.py`：`read()` 委托 `recall()`；管线抽出 `_diversify()`（近重复 + 会话上限）
- [x] 2.3 `_truncate_with_stats()`：返回选中 / 预算剔除数 / `minimum_budget`；`_truncate()` 兼容
- [x] 2.4 `RecallResult` 统计装配与不变式

## 3. 文档账

- [x] 3.1 `doc/02-modules/memory.md`：§3.19 多样性与统计
- [x] 3.2 `doc/03-interfaces/memory-interface.md`：`recall()` / `RecallResult`
- [x] 3.3 ADR-0294 + known-risk E240 + test-cases §217

## 4. 门禁与反证

- [x] 4.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`
- [x] 4.2 `uv run pytest -q` 全量全绿
- [x] 4.3 反证（`cp` + `md5sum`）：去近重复 / 去会话上限 / 多样性挪到预算后 / 统计硬编码
- [x] 4.4 `cd doc/openspec && openspec validate --all`
- [ ] 4.5 归档 / 提交（用户确认后）
