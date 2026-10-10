# memory Specification Delta — `reuse_count` 落盘持久化（change 0187）

## MODIFIED Requirements

### Requirement: 温度分层检索
系统 SHALL 提供**热/冷两档**检索，热数据常驻内存，冷数据按需加载；检索结果 SHALL 按
**多因子得分**排序——语义相似 × 层结构权重（加性）再经 新鲜度衰减、复用频次
（`1 + log1p(reuse_count)`）、主观重要度（`1 + importance`）**乘性调制**；条目 SHALL 携带
`kind`（episodic / semantic）与 `importance` 元数据，供下沉固化聚合。语义相似 SHALL 经
**可注入 embedder**（缺省词法、可远端向量化）计算，并对检索 query 与未变条目向量做**缓存**
（每次检索 query 至多向量化一次）。

命中条目的复用强化 SHALL **落盘持久化**：`reuse_count` 的递增 SHALL 写入持久后端
（SHALL NOT 只存在于进程内）—— 因该计数经 `1 + log1p(reuse_count)` 与
`freshness ** (1 / (1 + log1p(reuse_count)))` 参与排序与**遗忘曲线**调制，跨会话丢失强化会使
「反复被召回的条目」在重启后退化为从未复用 ⇒ 衰减不再被延缓。写回 SHALL **只**覆盖本次检索
**选中**（进入结果预算）的条目（非选中候选 SHALL NOT 被写、SHALL NOT 被强化 —— 与既有语义
逐字一致）⇒ 写放大有界于选中集。每条写回 SHALL 记录**可撤销效应**（按 trace 回滚即把
`reuse_count` 还原为强化前的值）。

#### Scenario: 热数据即时返回
- **GIVEN** 一个高频使用的 SOP
- **WHEN** 检索该 SOP
- **THEN** 从热区即时返回，无磁盘 IO

#### Scenario: 冷数据按需加载
- **GIVEN** 一个仅存在于 L4 的历史会话
- **WHEN** 检索命中冷数据
- **THEN** 异步加载并按预算注入上下文

#### Scenario: 检索失败降级
- **GIVEN** 检索主路径（热区/索引）发生异常或返回空结果
- **WHEN** 检索失败或未命中
- **THEN** 降级到全库扫描或返回明确未命中结果，不阻断 Agent 主流程，并记录失败原因

#### Scenario: 多因子排序
- **GIVEN** 两条候选记忆与查询的语义相似度相同
- **WHEN** 检索器排序候选
- **THEN** `importance` 更高或 `reuse_count` 更多的条目排在更前；命中条目的 `reuse_count` 递增

#### Scenario: 复用强化跨会话持久
- **GIVEN** 一条命中的记忆条目，其 `reuse_count` 在检索后递增并按预算落盘
- **WHEN** 以**同一持久后端**重新装载记忆（模拟进程重启 / 跨会话）
- **THEN** 该条目的 `reuse_count` 保持强化后的值（SHALL NOT 退回 0）；且该次写回 SHALL 可经
  trace 回滚而还原为强化前的值

#### Scenario: 语义相似经 embedder
- **GIVEN** 注入了 embedder
- **WHEN** 检索一个语义相近但词面不重叠的查询
- **THEN** 以向量相似度参与排序，且本次检索对 query 只向量化一次、未变条目复用缓存向量

#### Scenario: embedder 不可用降级词法
- **GIVEN** 未注入 embedder，或 embedder 调用抛错
- **WHEN** 检索器计算相似度
- **THEN** 降级为词法相似，检索不中断
