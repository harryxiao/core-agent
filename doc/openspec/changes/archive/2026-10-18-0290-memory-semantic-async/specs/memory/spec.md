# memory — 批量语义相似与异步上下文检索（change 0290）

## MODIFIED Requirements

### Requirement: 温度分层检索

系统 SHALL 提供**热/冷两档**检索，热数据常驻内存，冷数据按需加载；检索结果 SHALL 按
**多因子得分**排序——语义相似 × 层结构权重（加性）再经 新鲜度衰减、复用频次
（`1 + log1p(reuse_count)`）、主观重要度（`1 + importance`）**乘性调制**；条目 SHALL 携带
`kind`（episodic / semantic）与 `importance` 元数据，供下沉固化聚合。语义相似 SHALL 经
**可注入 embedder**（缺省词法、可远端向量化）计算，并对检索 query 与未变条目向量做**缓存**
（每次检索 query 至多向量化一次）。候选相似度 SHALL 按**有界批次**计算：一次检索的候选文本
合批后调用 embedder，每批一次调用（调用数为 O(候选数/批大小)），SHALL NOT 逐候选调用；
query SHALL 恒在第一批内。

**缺省词法相似** SHALL 按**词元 IDF 加权与文档长度归一**（BM25 口径）计算，SHALL NOT 对
所有查询词元等权、SHALL NOT 忽略文档长度；得分 SHALL 按查询词元的 IDF 总和归一并以 1 为上界
（与层结构权重同一量纲）。embedder 缺失或调用失败降级词法时 SHALL 使用同一 IDF/长度归一
口径。任一批 embedder 调用异常、返回向量数量与输入文本数不符、或向量维度不一致时，本次检索的
**全部候选** SHALL 降级为同一 IDF/长度归一化的词法相似，SHALL NOT 出现部分候选用余弦、
其余用词法的混合排序；候选集为空时 SHALL NOT 调用 embedder。组合根在**有效 embedding 模型
为空且 `llm.embedding_required` 关闭**时（既未显式配置 `llm.embedding_model`，也未按
`llm.embedding_auto` 从已知端点推导出模型）SHALL 在进程启动（CLI 入口）向 stderr 输出一次
「词法匹配、语义检索未启用」的提示，SHALL NOT 每轮检索重复输出；有效模型来自端点推导时
SHALL 输出一次「按端点自动选用 …（可用 `llm.embedding_model` 覆盖）」提示（不含端点与密钥）。
`llm.embedding_required` **开启**时，有效模型为空 SHALL 在**配置校验期阻断启动**（由
configuration 规格承载），组合根 SHALL NOT 进入本提示面。

`llm.embedding_required` 只保证「embedding 模型已确定」，SHALL NOT 探测网络可达性，
SHALL NOT 改变**调用期**降级语义：注入的 embedder 调用失败时仍 SHALL 降级为同一 IDF/长度
归一化的词法相似，检索不中断。

命中条目的复用强化 SHALL **落盘持久化**：`reuse_count` 的递增 SHALL 写入持久后端
（SHALL NOT 只存在于进程内）—— 因该计数经 `1 + log1p(reuse_count)` 与
`freshness ** (1 / (1 + log1p(reuse_count)))` 参与排序与**遗忘曲线**调制，跨会话丢失强化会使
「反复被召回的条目」在重启后退化为从未复用 ⇒ 衰减不再被延缓。写回 SHALL **只**覆盖本次检索
**选中**（进入结果预算）的条目（非选中候选 SHALL NOT 被写、SHALL NOT 被强化 —— 与既有语义
逐字一致）⇒ 写放大有界于选中集。每条写回 SHALL 记录**可撤销效应**（按 trace 回滚即把
`reuse_count` 还原为强化前的值）。

复用强化的**落盘** SHALL 按**单次检索批量提交**：后端支持批量写（`put_many`）时，一次检索的
全部选中条目 SHALL 经**一次批量落盘**写回（SHALL NOT 逐条触发全量重写）；后端未提供批量写时
SHALL 逐条写回（语义不变）。批量写 SHALL 与逐条写回**同一可撤销语义**：每条写回仍各记一条
可撤销效应，按 trace 回滚即把各自 `reuse_count` 还原为强化前的值。

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
- **GIVEN** 注入了 embedder，候选集有多条条目
- **WHEN** 检索一个语义相近但词面不重叠的查询
- **THEN** 候选按有界批次向量化（每批一次 embedder 调用），以余弦相似度参与排序；
  本次检索对 query 只向量化一次、未变条目复用缓存向量

#### Scenario: 运行中事件循环内语义检索不降级
- **GIVEN** `MemoryStore.read` 在**运行中事件循环**线程上被调用，且注入了可用的同步 embedder
- **WHEN** 检索器计算语义相似
- **THEN** 语义排序仍然生效，SHALL NOT 仅因 `asyncio.run` 在循环内不可用而降级词法

#### Scenario: 空候选集不触网
- **GIVEN** 候选集为空
- **WHEN** 检索器准备计算语义相似
- **THEN** 不调用 embedder（空读的瞬时失败不得置粘性降级、毒化后续检索）

#### Scenario: embedder 不可用降级词法
- **GIVEN** 未注入 embedder，或 embedder 调用抛错（含任一批失败、返回向量数量/维度不符）
- **WHEN** 检索器计算相似度
- **THEN** 本次检索的**全部**候选降级为 IDF/长度归一化的词法相似（罕见词元权重更高），
  SHALL NOT 混合余弦与词法两种尺度，检索不中断

#### Scenario: 罕见词元优先
- **GIVEN** 两条同层、同新鲜度、同复用与重要度的条目，各命中查询的一个词元
- **WHEN** 检索器按词法打分
- **THEN** 命中语料中**文档频率更低**（IDF 更高）词元的条目排在更前

#### Scenario: 长度归一
- **GIVEN** 两条条目命中同一查询词元，其一内容显著更长
- **WHEN** 检索器按词法打分
- **THEN** 较短（词元长度更接近语料平均）的条目排在更前

#### Scenario: 未配置 embedding 模型时启动提示
- **GIVEN** `llm.embedding_model` 未配置，`embedding_required` 关闭（缺省），且
  `embedding_auto` 关闭或端点未命中内置表
- **WHEN** CLI 入口装配运行时
- **THEN** stderr 输出一次「记忆检索使用词法匹配（语义检索未启用）」提示；有显式或推导模型时
  不输出该词法提示

#### Scenario: 端点推导启用语义检索
- **GIVEN** `llm.embedding_model` 未配置、`embedding_auto` 为缺省开启且 `endpoint` 主机命中
  内置端点表
- **WHEN** CLI 入口装配运行时
- **THEN** 记忆注入以推导模型构造的 embedder（语义检索生效），stderr 输出一次「按端点自动
  选用 …」提示，且不输出词法降级提示

#### Scenario: embedding_required 阻断空模型启动
- **GIVEN** `llm.embedding_required=true`，未显式配置 `embedding_model`，且端点未命中内置表
  （有效 embedding 模型为空）
- **WHEN** 系统加载配置
- **THEN** 校验期阻断启动；记忆装配与「词法匹配」启动提示均不进入（该路径不可达）

#### Scenario: embedding_required 不改变调用期降级
- **GIVEN** `llm.embedding_required=true` 且有效 embedding 模型非空，但远端调用
  `/embeddings` 失败
- **WHEN** 检索器计算相似度
- **THEN** 仍降级为 IDF/长度归一化的词法相似，检索不中断（required 不探测可达性）

#### Scenario: 复用强化批量落盘
- **GIVEN** 一次检索选中多条条目，且后端提供批量写入口
- **WHEN** 复用强化写回
- **THEN** 本次检索只触发**一次**批量落盘（不逐条重写），且每条仍各留一条可撤销效应
