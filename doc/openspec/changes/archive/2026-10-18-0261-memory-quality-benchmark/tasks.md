# Tasks 0261 — 记忆检索质量离线基准

## 1. 规格

- [x] 1.1 `memory` delta：ADDED「检索质量离线基准」（recall/MRR/陈旧命中阈值 + 3 scenarios）。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_memory_quality.py`：固定语料 + 12 查询；recall@5 ≥0.9、MRR@5 ≥0.7、
      stale_hits = 0；打印指标。
- [x] 2.2 排除用例：`exclude_source_prefixes=("bench.stale",)` 后无陈旧来源。
- [x] 2.3 确定性：两次独立重放 top-5 序列一致。

## 3. 实现

- [x] 3.1 仅测试与文档；不改生产代码（若基准揭示排序缺陷，另立 change 修复）。

## 4. 验证

- [x] 4.1 反证：改当前事实 / 摘排除过滤 / 让陈旧条目压过当前 ⇒ 对应用例红；复原后全绿。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0251；`coding-plan/known-risk.md` E197 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §173；`doc/02-modules/memory.md` 补检索质量门。
- [x] 5.3 单次提交 `feat(memory): ... change 0261 / ADR-0251 / 台账 E197`；更新记忆。
