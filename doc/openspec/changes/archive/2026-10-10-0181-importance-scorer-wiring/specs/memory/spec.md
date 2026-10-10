# memory Specification Delta — 重要度闸门内部产物豁免面（change 0181）

## MODIFIED Requirements

### Requirement: 写入侧重要度闸门（importance write gate）

系统 SHALL 支持注入 **importance scorer**（`MemoryStore` 构造形参，契约
`Callable[[MemoryEntry], float]`，返回 [0,1]）—— 与 `summarizer` / `embedder` /
`key_fact_extractor` 同一依赖方向：memory SHALL NOT import 任何 LLM / rag 抽象，评分器由
L5 组合根注入；**缺省 UNWIRED**。注入后，写入路径 SHALL 先评分再落库：

- 分值低于 `IMPORTANCE_FLOOR` 的条目 SHALL **拒绝入库**（不写、无效应记录、无条目产生），
  并 SHALL 经 `warnings.warn` 留痕（留痕 SHALL 含条目可识别摘要，SHALL NOT 泄露可能含密钥的正文全文）。
- 分值在 `IMPORTANCE_FLOOR` 与 `IMPORTANCE_AMBIT` 之间 ⇒ 条目 SHALL **降层写入 L4 归档层**
  （不拒收但降检索优先级），写入 SHALL 记可撤销效应。
- 分值不低于 `IMPORTANCE_AMBIT` ⇒ 条目按原意向层正常入库，且其 `importance` SHALL 被写为分值
  （写回 SHALL 记可撤销效应，与固化写回同口径）。
- 评分器抛错或返回界外值 ⇒ SHALL **降级放行**（不评分、不拒收、不降层，按原意向层写入），
  `warnings.warn` 留痕，SHALL NOT 牵连写入主流程。
- **未注入（缺省）⇒ 写入行为 SHALL 与现状逐字一致**：不评分、不拒收、不降层、不写 `importance`。
- **内部/派生产物豁免**：条目 `source` 属**豁免面**（`compaction` / `context` / `extraction` —— 分别
  对应会话摘要与中层摘要、上下文压实产物、结构化关键事实，皆由系统管道从**已准入**的材料派生）
  ⇒ 条目 SHALL NOT 经评分（不拒收、不降层、不写 `importance`），其写入 SHALL 与该条目不注入评分器时
  **逐字一致**（派生结论 SHALL NOT 因评分而丢失或降层）。

#### Scenario: 未注入评分器时写入不变
- **GIVEN** 未注入 importance scorer 的 `MemoryStore`
- **WHEN** 写入一条条目
- **THEN** 落库层与内容与既有行为逐字一致，无评分留痕、无额外效应

#### Scenario: 低分条目拒收
- **GIVEN** 注入了 scorer，其对该条目返回 0.1（低于 `IMPORTANCE_FLOOR`）
- **WHEN** 写入该条目
- **THEN** 条目不落库（`audit()` 无变化）、无效应记录，且 `warnings.warn` 留痕

#### Scenario: 中间分降层写入
- **GIVEN** 注入了 scorer，其返回 0.3（`IMPORTANCE_FLOOR` ≤ 分 < `IMPORTANCE_AMBIT`）
- **WHEN** 写入该条目
- **THEN** 条目落至 L4 归档层，且该写入可撤销（回滚即按原意向层恢复）

#### Scenario: 高分正常入库并写回分值
- **GIVEN** 注入了 scorer，其返回 0.8
- **WHEN** 写入该条目
- **THEN** 条目按原意向层入库，`importance` 被写为 0.8，且该写回可撤销

#### Scenario: 评分器抛错降级放行
- **GIVEN** 注入的 scorer 调用时抛错
- **WHEN** 写入一条条目
- **THEN** 条目按原意向层正常入库，`warnings.warn` 留痕，写入主流程不中断

#### Scenario: 内部派生产物豁免评分
- **GIVEN** 注入了 scorer，其对任何条目返回 0.1（低于 `IMPORTANCE_FLOOR`）
- **WHEN** 写入一条来源属豁免面（如 `source="compaction"` 的会话摘要 / 中层摘要）的派生条目
- **THEN** 条目按原意向层入库、不降层、不写 `importance`，且**无**评分留痕（派生结论不因评分而丢失）

#### Scenario: 非豁免来源（loop）仍受评分
- **GIVEN** 注入了 scorer，其对任何条目返回 0.1
- **WHEN** 写入一条来源**非**豁免面的条目（如 `source="loop"` 的轨迹条目）
- **THEN** 条目被**拒收**（不落库）、`warnings.warn` 留痕 —— 豁免面只覆盖系统派生产物
