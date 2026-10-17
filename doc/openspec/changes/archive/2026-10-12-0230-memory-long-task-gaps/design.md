# Design 0230: 记忆机制长任务支持缺口修复

## 架构决策

### G1 — 可注入的 Token 估算器

- 新增 `TokenEstimator` 协议接口（`typing.Protocol`），签名 `estimate(text: str) -> int`。
- 缺省实现 `HeuristicEstimator`：保持现有「约 4 字符 ≈ 1 token」启发式，**行为不变**。
- `src/core/context/budget.py:17` 与 `src/core/memory/store.py:43` 的内联估算改为调用注入的估算器；构造函数/配置注入，未注入时回落启发式。
- 显式注入精确 tokenizer（如 tiktoken 封装）后，预算测量替换启发式估算。

### G2 — 溢出降级续跑

- `src/core/loop/default.py`（现 L499-501）的 `TOKEN_BUDGET_EXCEEDED` break 改造为两段式：
  1. 预算触顶时先触发一次强制 compaction（复用 change 0182 的 `compacted` 闸门防重入）；
  2. 压实后重试一轮；重试后仍 `token_used >= token_budget` 才发 `TOKEN_BUDGET_EXCEEDED` 终止。
- 重试标记（`budget_retried: bool`）防止无限循环——每轮循环最多降级一次。

### G5 — L2 活跃层软上限

- store 新增 `l2_soft_max_entries` 配置（缺省 `None` = 不启用，行为不变）。
- 写路径后**触发式**检查活跃层条目数：超限即调用既有 `forget(threshold)` 与 L4 迁移路径归档最旧条目；不阻塞写入，不新增删除语义。

### G4 — KeyFact 跨批次按 slug 合并

- `store._plan_key_facts`（现 L162-192）扩展：按 `slug_entity` 检索既有 L2 keyfact——同实体命中时**更新既有条目 value**（新值覆盖，含留痕）而非新增，并保留首次出现时间戳。
- 批内归并语义（change 0172：留首条、留痕含实体名不含取值、不占额度）保持不变。

### G7 — 缺省文件型 checkpoint

- `scheduler.py` 提供缺省 `FileCheckpoint` 实现（dataclass，满足既有 `CheckpointFn` 协议）。
- JSON 单文件落盘 `plan/completed/results` 三元组；原子写（tmp + rename）；路径可配置，缺省 `.core/scheduler-checkpoint.json`。
- 上层注入仍可覆盖（回调契约不动）。

## 明确不做（决策记录）

- **G3**（摘要依赖注入模型才生效）：ADR-0045 刻意的保守缺省设计，本 change 不改。
- **G6**（`_elide_summary` 首尾截断丢中段）：已有省略标记，可接受，仅记录不改。
- 抽取端 LLM 主题聚类：行为变更，另行提案。

## 风险与缓解

- G2 降级续跑可能掩盖预算配置过小的真实问题 → 压实重试发生时记入日志/观测，可被诊断（对齐 observability 能力）。
- G5 软上限误删高价值条目 → 只走既有 `forget` 打分路径，不做新删除逻辑。
- G7 checkpoint 文件含任务结果 → 不含密钥（记忆写入前已有 `redact_secrets` 约束）。
