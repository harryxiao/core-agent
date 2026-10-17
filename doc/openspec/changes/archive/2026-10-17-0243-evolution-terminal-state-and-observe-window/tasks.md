# Tasks — evolution：pending 终态化 ＋ 观察期滑动窗口

## 1. 规格

- [x] 1.1 `evolution/spec.md`「人工确认队列的持久化与操作面」MODIFIED：终态化 + 恢复 fail-closed + 3 Scenario
- [x] 1.2 `evolution/spec.md`「观察期回归自动溶解」MODIFIED：样本窗口 + 基线口径 + 3 Scenario
- [x] 1.3 `openspec validate 2026-10-17-0243-evolution-terminal-state-and-observe-window`

## 2. 红测试

- [x] 2.1 门禁拒绝候选 `status="rejected"` 且不在 `pending()`
- [x] 2.2 rollback 候选 `status="rejected"` 且不在 `pending()`；freeze 候选 `status="frozen"`
- [x] 2.3 损坏记录（缺 kind/risk/status）恢复为 `plugin` / `high` / 非 pending
- [x] 2.4 观察窗口样本上界（含 reload）与滑动均值
- [x] 2.5 早期好样本不稀释近期回归（累计均分反例）
- [x] 2.6 采样不改写基线

## 3. 实现

- [x] 3.1 `run_cycle` 三分支落盘前置终态；`models.py` 状态词表注释补 `frozen`
- [x] 3.2 `pending._candidate_from_dict` 缺省 fail-closed
- [x] 3.3 `ObservationRegistry(max_samples=64)` + 超界淘汰 + `_load` 裁剪
- [x] 3.4 docstring/接口文档同步基线口径

## 4. 门禁与反证

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`
- [x] 4.5 反证：摘终态化 ⇒ 3 红；摘滑窗裁剪 ⇒ 2 红；恢复缺省回 fail-open ⇒ 1 红；复原 md5 同

## 5. 收口

- [x] 5.1 归档到 `doc/openspec/changes/archive/2026-10-17-0243-evolution-terminal-state-and-observe-window/`
- [x] 5.2 ADR-0231 + 变更追踪表
- [x] 5.3 台账 E178（`known-risk.md` §1/§3）+ 测试节 §154（`test-cases.md`）
- [x] 5.4 接口文档同步（`evolution-interface.md`）
- [ ] 5.5 单次提交（change 0243 / ADR-0231 / 台账 E178）
