## ADDED Requirements

### Requirement: 检索规模离线基准（1 万条）

系统 SHALL 提供**离线、确定性**的记忆检索规模基准：固定 **1 万条**合成事实语料（覆盖
L2 / L3 / L4、每条带唯一锚点）＋ 20 条带 gold 的查询，度量 **recall@5**、**MRR@5** 与
**逐查询延迟**（中位 / p95 / max）。

- 基准 SHALL NOT 依赖 embedder、真实 LLM 或网络；SHALL 使用纯内存后端。
- 准确率门禁：recall@5 ≥ `0.9`、MRR@5 ≥ `0.7`。
- 延迟 SHALL 被**报告**并与 CORE-NFR-PERF2（`<100ms` / 1 万条）对照；本基准 SHALL NOT 以该
  产品目标作为硬门禁（当前实现未达标，修复另行立项），仅 SHALL 设宽松回归上限
  （p95 `< 5000ms`）防止整体恶化一个数量级。
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
- **AND** 未达产品目标 SHALL NOT 使基准转红；仅 p95 ≥ `5000ms`（整体恶化）时转红

#### Scenario: 语料确定性
- **GIVEN** 同一确定性生成器
- **WHEN** 独立生成两次语料
- **THEN** 两次逐条的 `(id, layer, content)` 一致
