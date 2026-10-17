# Tasks 0230: 记忆机制长任务支持缺口修复

> 只做 G1/G2/G5/G4/G7 的确定性子集；G3/G6 属 ADR-0045 刻意设计，仅记录不改。

- [x] 1. **T1 G1 — Token 估算器注入**
  - [x] 新增 `TokenEstimator` 协议 + `HeuristicEstimator` 缺省实现（行为不变）
  - [x] `context/budget.py`、`memory/store.py` 的内联启发式改为调用注入估算器
  - [x] 提供注入路径（constructor/config），未注入回落启发式
  - [x] 测试：缺省启发式路径与注入精确 tokenizer 双路径数值一致
- [x] 2. **T2 G2 — 溢出降级续跑**
  - [x] `loop/default.py` 预算触顶先触发一次强制 compaction（复用 change 0182 `compacted` 闸门防重入）
  - [x] 压实后重试一轮；二次仍超限才 `TOKEN_BUDGET_EXCEEDED` 终止；`budget_retried` 标记防无限循环
  - [x] 压实重试发生时记入日志/观测（便于诊断预算配置过小）
  - [x] 测试：「一次降级成功续跑」与「二次超限终止」两用例
- [x] 3. **T3 G5 — L2 活跃层软上限**
  - [x] store 新增 `l2_soft_max_entries` 配置（缺省 None 不启用）
  - [x] 写路径后触发式检查，超限走既有 `forget(threshold)` + L4 迁移，不阻塞写入
  - [x] 测试：超限触发 forget 归档、未启用时行为不变
- [x] 4. **T4 G4 — KeyFact 跨批次合并**
  - [x] `_plan_key_facts` 扩展：按 `slug_entity` 检索既有 keyfact，命中即更新 value（新值覆盖、含留痕、保留首见时间戳）而非新增
  - [x] 批内归并语义（change 0172）保持不变
  - [x] 测试：跨批次同 slug 不新增条目、value 更新、时间戳保留；批内行为回归
- [x] 5. **T5 G7 — 缺省文件型 checkpoint**
  - [x] `scheduler.py` 提供 `FileCheckpoint`（dataclass，满足 `CheckpointFn` 协议）
  - [x] JSON 单文件落盘 plan/completed/results；原子写（tmp+rename）；路径可配置，缺省 `.core/scheduler-checkpoint.json`
  - [x] 上层注入仍可覆盖
  - [x] 测试：落盘与加载恢复；注入覆盖路径
- [x] 6. **T6 — 文档与规格同步**
  - [x] spec delta：memory（G4/G5）、agent-loop（G1/G2）、orchestration（G7）
  - [x] `openspec validate` 全绿
  - [x] 记录 G3/G6 决策（ADR-0045 引用，明确不改理由）
- [x] 7. **T7 — 验证收尾**
  - [x] lint / typecheck / test / build 全绿
  - [x] 提交：`fix(memory): change 0230`（一个 commit 对应一个 change）
  - [x] 归档 change 0230 目录
