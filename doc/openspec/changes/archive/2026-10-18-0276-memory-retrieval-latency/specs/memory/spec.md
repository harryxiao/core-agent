# Memory Specification Delta — 检索延迟修复（change 0276）

## MODIFIED Requirements

### Requirement: 检索规模离线基准（1 万条）

系统 SHALL 提供**离线、确定性**的记忆检索规模基准：固定 **1 万条**合成事实语料（覆盖
L2 / L3 / L4、每条带唯一锚点）＋ 20 条带 gold 的查询，度量 **recall@5**、**MRR@5** 与
**逐查询延迟**（中位 / p95 / max）。

- 基准 SHALL NOT 依赖 embedder、真实 LLM 或网络；SHALL 使用纯内存后端。
- 准确率门禁：recall@5 ≥ `0.9`、MRR@5 ≥ `0.7`。
- 延迟 SHALL 被**报告**并与 CORE-NFR-PERF2（`<100ms` / 1 万条）对照；产品目标 SHALL NOT
  作为跨机硬门禁（`0276` 修复后参考机实测中位 ≈83ms），仅 SHALL 设回归上限
  （p95 `< 1000ms`，相对参考机修复后实测 ≈109ms 留约 9× 余量）防止整体恶化一个数量级。
- 语料 SHALL 由确定性生成器产出，两次独立生成逐条一致；语料或阈值变更 SHALL 视为
  **显式重定基线**并记录原因。

#### Scenario: 规模与准确率
- **GIVEN** 1 万条固定合成语料与 20 条带 gold 查询
- **WHEN** 逐条执行离线检索
- **THEN** store 恰好持有 1 万条，且 recall@5 ≥ `0.9`、MRR@5 ≥ `0.7`

#### Scenario: 延迟可度量
- **GIVEN** 同一语料与查询集
- **WHEN** 逐条计时
- **THEN** 输出延迟的中位 / p95 / max，并与 `<100ms` 产品目标对照
- **AND** 未达产品目标 SHALL NOT 使基准转红；仅 p95 ≥ `1000ms`（整体恶化）时转红

#### Scenario: 语料确定性
- **GIVEN** 同一确定性生成器
- **WHEN** 独立生成两次语料
- **THEN** 两次逐条的 `(id, layer, content)` 一致

## ADDED Requirements

### Requirement: 检索词元缓存（有界、按内容失效）

系统 SHALL 在记忆检索的候选集分词中复用**按条目内容校验**的词元缓存：同一存储实例上对
**内容未变**的条目 SHALL 复用已计算的词元集（SHALL NOT 每次检索重复分词）；同 `id` 覆写
**内容变更**后，旧词元集 SHALL 失效并重新计算。

- 缓存 SHALL 有上界（FIFO 淘汰），SHALL NOT 随历史条目无界增长。
- 复用 SHALL NOT 改变检索语义：排序得分、预算裁剪与命中集合 SHALL 与未启用缓存时逐条一致。
- 词元缓存 SHALL 只以 `content` 为有效性判据，SHALL NOT 缓存随时间变化的字段
  （`reuse_count` / `importance` 等）。

#### Scenario: 重复检索复用
- **GIVEN** 同一存储实例已对固定语料执行过一次检索
- **WHEN** 再次执行同一查询
- **THEN** 未变条目 SHALL NOT 被重新分词（第二次检索只对查询分词），且结果与首次逐条一致

#### Scenario: 内容变更失效
- **GIVEN** 某条目的词元集已在缓存中
- **WHEN** 以同一 `id` 覆写不同内容后再次检索
- **THEN** SHALL 使用新内容的词元集参与打分（旧词元 SHALL NOT 残留）

#### Scenario: 有界淘汰
- **GIVEN** 缓存条目数达到上界
- **WHEN** 继续检索更多条目
- **THEN** 缓存条目数 SHALL 不超过上界，且检索结果不受淘汰顺序影响
