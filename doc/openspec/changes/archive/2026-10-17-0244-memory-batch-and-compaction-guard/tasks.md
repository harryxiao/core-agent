# Tasks — memory：复用强化批量落盘 ＋ 空摘要守卫 ＋ 教训块预算

## 1. 规格

- [x] 1.1 `memory/spec.md`「温度分层检索」MODIFIED：批量写回 + 1 Scenario
- [x] 1.2 `memory/spec.md`「记忆压实」MODIFIED：空摘要跳过派生抽取 + 1 Scenario
- [x] 1.3 `loop/spec.md`「执行循环」MODIFIED：教训块有界 + 1 Scenario
- [x] 1.4 `openspec validate 2026-10-17-0244-memory-batch-and-compaction-guard`

## 2. 红测试

- [x] 2.1 一次检索的复用强化只触发一次 `put_many`、零次 `put`
- [x] 2.2 无 `put_many` 的鸭子类型后端仍逐条 `put`（语义回退）
- [x] 2.3 `_hot` 有界（≤512）且全量条目仍可见；被淘汰条目 importance 撤销回退冷区
- [x] 2.4 空摘要跳过派生抽取（0 调用）并留痕、原条目层级不变
- [x] 2.5 教训块单条 ≤500 / 总正文 ≤1500

## 3. 实现

- [x] 3.1 `FileBackend.put_many`（单次 `_persist`）
- [x] 3.2 `_reinforce` 批量递增 + 回退；逐条效应不变
- [x] 3.3 `_hot_put` + `_HOT_MAX=512`；`_restore_importance` 冷区回退
- [x] 3.4 空摘要 `warnings.warn` + `continue`
- [x] 3.5 `runtime._render_failure_lessons` 纯函数 + 常量；闭包改调它
- [x] 3.6 接口/模块文档同步

## 4. 门禁与反证

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`
- [x] 4.5 反证：摘 `put_many` 分支 ⇒ 1 红；摘 `_hot` 裁剪 ⇒ 1 红；摘空摘要 `continue` ⇒ 1 红；
      摘教训截断 ⇒ 1 红；复原 md5 同

## 5. 收口

- [x] 5.1 归档到 `doc/openspec/changes/archive/2026-10-17-0244-memory-batch-and-compaction-guard/`
- [x] 5.2 ADR-0232 + 变更追踪表
- [x] 5.3 台账 E179（`known-risk.md` §1/§3）+ 测试节 §155（`test-cases.md`）
- [x] 5.4 接口文档同步（`memory-interface.md`）
- [x] 5.5 单次提交（change 0244 / ADR-0232 / 台账 E179）
