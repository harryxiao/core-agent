# Tasks — memory-compaction-hardening

> 由 `/tmp/0255-memory-compaction-hardening.draft/design.md` 的 Migration Plan 还原。
> 原草稿编号 0255；该号已被 `2026-10-17-0255-skill-extraction-quality` 占用，本 change 改用 0258。

## 1. 规格 delta

- [ ] 1.1 `memory`：摘要分层保留（结论区/事实区独立预算 + 分层 elide + 无标记回退）
- [ ] 1.2 `context`：预算裁决单一口径（`BudgetManager.should_compact`；`_should_compact` 仅触发）
- [ ] 1.3 `orchestration`：checkpoint 原子写 + 损坏降级留痕

## 2. 实现

- [ ] 2.1 `src/core/context/budget.py`：新增 `should_compact`（纯新增，旧调用方零影响）
- [ ] 2.2 `src/core/loop/default.py`：`_should_compact` 调用点切换为 `budget.should_compact(...)`
- [ ] 2.3 `src/core/memory/summarize.py`：分层 elide + merge prompt 更新（无标记回退整段 elide）
- [ ] 2.4 `src/core/memory/store.py`：摘要长度/提升边界与新分层常量对齐
- [ ] 2.5 `src/core/orchestration/scheduler.py`：默认 checkpoint 原子写 + 损坏 JSON 降级留痕

## 3. 测试

- [ ] 3.1 新增 `tests/test_memory_compaction_hardening.py`：分层 elide（含无标记旧摘要回退）
- [ ] 3.2 预算口径一致：预算关闭退化为步数阈值，阈值边界与旧行为逐字一致
- [ ] 3.3 checkpoint 原子写（无 `.tmp` 残留）与损坏 JSON 降级（不抛、可观测）
- [ ] 3.4 反证：逐项摘除新增分支，对应用例红；复原后 md5 同

## 4. 门禁与收口

- [ ] 4.1 `.venv/bin/ruff check src tests`
- [ ] 4.2 `.venv/bin/ruff format --check src tests`
- [ ] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [ ] 4.4 `.venv/bin/pytest -q`
- [ ] 4.5 `openspec validate --all`
- [ ] 4.6 ADR / 台账（E 编号）/ 测试节（§ 编号）/ 接口文档
- [ ] 4.7 `openspec archive 2026-10-17-0258-memory-compaction-hardening --yes`
- [ ] 4.8 单次提交 `fix(memory): ... change 0258`
