# context Specification Delta — 压缩产物退出事实注入面（change 0185）

## MODIFIED Requirements

### Requirement: 动态上下文构建
系统 SHALL 以**任务目标**为检索信号按需加载上下文（L2 事实检索以 task 为 query；stage 为装配阶段标注、
暂不参与事实选择），控制注入 token 上界，超预算裁剪低相关度内容。装配 SHALL 另接受可选的**调用方会话标识**
`session_id` 并**透传**至 L2 事实检索，作为该次检索的会话维度；标识缺省空串时，检索语义与既往**逐字一致**。

装配 SHALL 另支持**可选的事实面排除面** `exclude_fact_sources`（按 `MemoryEntry.source` **前缀**匹配；
缺省空 ⇒ **不含排除**、装配结果与既往**逐字一致**）：**已由专块注入**的压缩产物 SHALL NOT 再次进入
「相关事实」注入面 —— 会话长期 / 中期摘要（`source` 为 `compaction`）的正文 SHALL 只经「历史摘要（长期）」
/「历史摘要（中期）」专块承载，同一份内容 SHALL NOT 经两条通道重复注入同一次请求（对齐 `notes`「会话摘要
提升」的**同型纪律**）。该排除 SHALL **只**落在装配面的**注入步骤**：`MemoryStore.read` 的检索语义、排序、
预算与复用强化 SHALL **逐字不变**（`compaction.*` 条目对其他消费者 —— 抽取素材、检索素材、CLI 查询 ——
仍可见）；**无**专块承载的压缩产出（`source` 为 `context`，如压缩产出的事实 / 未决事项）SHALL **不受影响**。

#### Scenario: 按需加载与预算控制
- **GIVEN** 一个任务处于某阶段
- **WHEN** 上下文装配器构建上下文
- **THEN** 以任务目标为检索信号加载相关事实，token 控制在预算内

#### Scenario: 按任务召回事实
- **GIVEN** MemoryStore 含与当前任务相关的历史事实
- **WHEN** 上下文装配器以该任务构建上下文
- **THEN** 命中与任务相关的事实并注入 `facts`（检索 query 为 task，非阶段名）

#### Scenario: 会话维度透传
- **GIVEN** 一次携带会话标识的装配，且库中含他会话的事实
- **WHEN** 装配器构建上下文
- **THEN** 事实检索以该会话标识为会话维度，他会话事实**不进入** `facts`

#### Scenario: 压缩产物不进事实面
- **GIVEN** 会话已产出长期 / 中期摘要（`source` 为 `compaction`），其内容与当前任务检索命中；
  且库中同时含同一次压实产出的事实 / 未决条目（`source` 为 `context`）
- **WHEN** 装配器以排除面 `("compaction",)` 构建上下文
- **THEN** 长期 / 中期摘要**不出现**在 `facts` 中（其正文仍经「历史摘要」专块每轮注入 ⇒ 可见性不变、
  通道从二变一），而 `source` 为 `context` 的条目**仍在** `facts` 中；**未**传排除面时两者**都在**
  `facts` 中（与既往**逐字一致**）

#### Scenario: 超预算裁剪保留关键
- **GIVEN** 装配结果 token 超预算
- **WHEN** 预算管理器裁剪
- **THEN** 裁剪低相关度内容，优先保留宪章/未决事项/验收标准
