# Proposal — 记忆指标与效果评测（P2-5）

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §11.1「指标」/ §11.2「运维命令」/ §11.3「效果评测」
与走查 **P2-5**（`无 memory.* 指标；无「有/无记忆」效果评测`）：

1. **运行指标缺失**：`recall()` 已计算候选数 / 注入数 / 预算与多样性剔除数（change 0304），
   但装配器读的是 `read()` 的**条目列表**，统计在调用边界被丢弃；写入、幂等重放、巩固耗时
   也无任何累计计数。SDD 的 `memory.writes{kind}` / `memory.recall.candidates` /
   `memory.recall.injected_tokens` / `memory.consolidation.*` 在 `src/core` 下**零实现**。
2. **运维统计缺失**：SDD §11.2 的 `memory stats` 未提供。治理审计日志（change 0308）、
   条目状态与存储体积已在盘上，但只能逐条 `memory list` / `memory audit` 翻看，无法一次
   得到「写入分布 / 墓碑数 / 存储字节 / 删除与遗忘计数」。
3. **召回解释缺失**：SDD §11.2 的 `memory why <query>` 未提供；0304 / 0309 的 proposal 已把
   `why/stats` 显式登记为 P2-5 另行立项。
4. **缺任务级效果评测**：已有检索质量（0261）、规模（0275/0276）、分区权重（0277）、
   语义桥接（0289）基准，但都只测**检索返回了什么**；SDD §11.3 要求回放固定任务集，对比
   **有 / 无记忆**对任务成功率的影响。

本 change 只补**观测与评测面**，不改记忆语义：指标是进程内计数（零 I/O、零内容），
`memory stats` 从既有持久数据只读聚合，`memory why` 是**零强化**的诊断检索，
效果评测是离线确定性基准（零网络、零真实模型）。

## What Changes

- **`RecallResult` 扩充**（加性、缺省兼容）：新增 `injected_tokens`（注入条目 token 估算总和）
  与 `scores`（与 `entries` 同序的相关度分值；空结果 ⇒ 空列表）。`matched_count ==
  injected_count + excluded_by_diversity + excluded_by_budget` 不变。
- **`recall()` / `read()` 新增 `reinforce: bool = True`**：`False` ⇒ 不 `reuse_count` 自增、
  不写回、不记效应（供 `memory why` 等诊断面使用）；缺省 `True` ⇒ 既有语义逐字不变。
- **`MemoryStore.metrics_snapshot()`**：进程内累计指标（零 I/O、不含正文/查询）：
  - `memory.writes.<kind>`（成功落库数，按 `kind` 分组，键名规范化）、
    `memory.writes.deduped`、`memory.writes.rejected`；
  - `memory.recall.calls` / `.candidates` / `.injected` / `.injected_tokens` /
    `.excluded_by_budget` / `.excluded_by_diversity`；
  - `memory.consolidation.runs` / `.failures` / `.elapsed_ms`。
  巩固内部为决策打分触发的**读**不计入 recall 指标（不虚增注入统计）。
- **`memory stats [--json]`**：只读聚合既有持久数据 —— 条目（总数 / active / retracted /
  superseded / forgotten）、各层 active 计数、active 正文字节、`memory.jsonl` 文件字节、
  审计日志派生的写入分布 / 删除与遗忘计数（按 reason）/ 导出次数。缺文件 ⇒ 0；坏行跳过；
  **零强化**（只用 `audit(None)`，不走检索路径）。
- **`memory why <query> [--budget N] [--session S]`**：按 rank 序打印注入条目（score / 层 /
  kind / source / session / id / importance / reuse_count / 脱敏单行摘要）＋统计行
  （matched / injected / excluded_by_diversity / excluded_by_budget / minimum_budget /
  injected_tokens）；**零强化**（`reinforce=False`）；无命中 ⇒ 仍以 0 退出。
- **离线效果评测** `tests/test_memory_effectiveness.py`：固定任务集（问题 + gold 答案 +
  对应 gold 事实 + 干扰事实），用**真实** `DefaultLoop` + `LLMPlanner` + `DynamicAssembler`
  与桩 provider 回放两臂 —— 有记忆（灌入 gold 事实）/ 无记忆（空库）；度量成功率、
  prompt token、轮数、墙钟（只报告不设阈值）。断言：有记忆成功率 ≥ 0.9 且严格高于无记忆；
  零网络、零真实模型、零时钟噪声（桩 provider 只依据 prompt 是否含 gold 事实作答）。
- **不新增配置键**：计数器是既有调用路径上的记账；`stats` / `why` 是显式只读命令。

## Out of Scope（明确不做）

- **不落盘运行计数**：不在读路径追加事件（0308 已拒绝读路径审计的写放大），不新建
  metrics JSONL，不做跨进程聚合；进程内计数在进程退出时归零（文档登记）。
- **不做 `memory.recall.hit_rate`**：本仓无「召回后是否有用」的反馈通道；`memory.conflicts`
  无冲突概念；`memory.skill.*` 属技能/进化面，不并入本 change。
- **不做持久化指标导出协议 / Prometheus/OTel**：`MetricsCollector` 与本 change 不接线
  （0253 已裁决 trace 事件与指标聚合是两条面）。
- **不改检索排序 / 预算 / 多样性语义**；不记录查询正文到任何持久面。
