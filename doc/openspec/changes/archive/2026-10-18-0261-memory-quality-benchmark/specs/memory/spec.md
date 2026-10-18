## ADDED Requirements

### Requirement: 检索质量离线基准

系统 SHALL 提供**离线、确定性**的记忆检索质量基准，作为排序与分词口径的回归门：固定合成语料
（覆盖 L2 / L3 / L4、跨会话条目与陈旧冲突事实）＋ 带标注相关条目的查询集，度量 **recall@5**、
**MRR@5** 与**陈旧命中**（`bench.stale` 条目排名高于对应当前事实的查询数）。基准 SHALL 以
pytest 阈值门禁：recall@5 ≥ `0.9`、MRR@5 ≥ `0.7`、陈旧命中 = `0`。

- 基准 SHALL NOT 依赖 embedder、真实 LLM 或网络；SHALL 使用纯内存后端。
- 每条查询 SHALL 以**新建 store** 重放固定语料，避免检索强化（`reuse_count` 改写）造成查询
  顺序耦合；同一语料的两次独立重放 SHALL 返回相同的 top-5 序列。
- 语料或阈值变更 SHALL 视为**显式重定基线**并记录原因，SHALL NOT 为让现有实现变绿而静默放宽。

#### Scenario: 合成语料基线达标
- **GIVEN** 固定合成语料与带 gold 的查询集
- **WHEN** 逐条查询执行离线基准
- **THEN** recall@5 ≥ `0.9`、MRR@5 ≥ `0.7`、陈旧命中 = `0`

#### Scenario: 陈旧来源可排除
- **GIVEN** 语料含 `source="bench.stale"` 的陈旧条目
- **WHEN** 检索时传入 `exclude_source_prefixes=("bench.stale",)`
- **THEN** 返回结果不含任何 `bench.stale` 来源条目（排除发生在排名与预算之前）

#### Scenario: 重放确定性
- **GIVEN** 同一固定语料
- **WHEN** 以两个独立的新 store 分别重放并执行同一查询
- **THEN** 两次返回的 top-5 条目 id 序列一致
