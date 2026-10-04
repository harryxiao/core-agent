# Proposal: 记忆固化与遗忘（consolidation + forgetting）

## Why

Phase 18 #4/#5（M4 自进化收口）。0039 已给 `MemoryEntry` 加 `importance` 元数据、0041 已打通
「会话摘要 → semantic 条目 + L4 归档」的提炼通道，但两处仍是空的：

1. **`importance` 从未被自动打分**：字段默认 `0.0`，全仓无任何写入点（0039 明确「自动打分留至
   #4/#5」）→ 多因子重排里的 `(1 + importance)` 恒为 1，主观重要度维度形同虚设。
2. **无固化（consolidation）**：0041 的会话摘要对**所有**会话无差别提炼——没有「这条轨迹值不值得
   沉淀」的价值判断，低价值会话（一轮寒暄、无行动）也照样产出 semantic 条目，稀释记忆质量。
3. **无遗忘（forgetting）**：记忆只增不减。陈旧且从未复用的 episodic 条目永久占据 L2、
   参与每次检索排序；memory spec 只要求「归档过期会话」，但没有任何实现动作。

规格侧：memory spec 的「记忆压实」只覆盖合并/归档/索引最小化，**「固化」与「遗忘」两条
Requirement 均不存在**（本次新增）。

## What Changes

- **ADDED Requirement: 记忆固化（consolidation）**——`importance` 经 judgment `score` 原语自动
  打分并写回条目（可逆）；会话摘要提炼加**价值门控**：分值达阈值的会话才提炼为 semantic 条目，
  低价值会话保留 episodic 原样。
- **ADDED Requirement: 记忆遗忘（forgetting）**——衰减评分（新鲜度 × 复用 × 重要度）低于阈值的
  L2 episodic 条目**迁 L4 归档**（不删除、`audit` 可见），逐条记可逆效应；semantic / L0 / L3 不受影响。
- 两条能力并入既有压实链路（`MemoryStore.compact` 的价值门控 + 新增 `MemoryStore.forget`），
  触发点复用 loop 的压实触发（`persist → compact → forget`），**不新增触发面、不改终止语义**。

## Non-goals

- **跨会话/跨主题固化**：仍按 `session_id` 分组（与会话摘要同口径）；主题聚类需要 embedder 在线
  且质量难离线断言，另立变更。
- **物理删除**：遗忘只迁层，永不 delete（可 `audit`、可回滚）。
- **并发锁**：仓库是单线程事件循环，无并发调用方（同 0041 的已知缺口）。
- **fix 生产侧 `session_id` 为空串**：session 透传是另一件事（0041 遗留），本次不扩大范围。

## Impact

- 规格：`memory/spec.md`（+2 Requirement）。
- 代码：`memory/store.py`（`compact` 价值门控 + `_score_importance` + `forget` + `_decay_score`）、
  `loop/default.py`（压实触发增遗忘一步）。
- 契约：`doc/03-interfaces/memory-interface.md`（`forget` 与打分/门控语义）+ ADR-0047。
- 兼容性：未注入 scorer 时不打分也不设门槛（保持 0041 行为）；未注入 summarizer 时固化整条
  通道不激活；`forget` 是**新增**方法，调用方显式触发。**loop spec 不变**（既有 Scenario 覆盖
  预算超限触发压实；遗忘为其延伸，不改变终止语义）。

## Risks

- **LLM 调用成本**：`score` 原语返回的是「条目集」单一分数，逐条目重要性须**每条一次调用** →
  以 `_MAX_SCORED_PER_COMPACT` 设上界（按本地多因子序取前 N 条），超界条目本轮不打分。
- **误遗忘**：阈值过松会归档仍需要的记忆 → 只迁层不删除 + 可回滚 + 只作用 L2 episodic；
  阈值取 0.05（≈19 天零复用零重要），语义层与 L0/L3 不受影响。
- **打分质量依赖 JEV/主 LLM**：无条件回退主 LLM（judgment 既有语义），不可达时该轮不打分
  （`importance` 保持原值，不写 0）。
