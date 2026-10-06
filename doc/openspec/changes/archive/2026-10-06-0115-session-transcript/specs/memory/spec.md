# Memory Specification Delta

## MODIFIED Requirements

### Requirement: 分层记忆模型
系统 SHALL 按 L0（元策略）→L1（索引）→L2（事实）→L3（SOP/技能）→L4（归档层：遗忘与压实的下沉目标，检索降权、不参与固化）分层存储，层间由轻量索引连通；并 SHALL 在 L2 写入时记录条目的**会话归属**（`session_id`，缺省空串表示未归属会话）——压实、固化与遗忘的「按会话」口径（见「记忆压实」「记忆固化」）一律以该字段归组。

#### Scenario: 分层写入
- **GIVEN** 一条经验需要沉淀
- **WHEN** 记忆系统判断其层级
- **THEN** 写入对应层级，并在 L1 建立最小索引条目

#### Scenario: 写入记录会话归属
- **GIVEN** 一轮属于某会话（`session_id` 非空）的执行产生 L2 沉淀
- **WHEN** 条目写入记忆存储
- **THEN** 该条目的 `session_id` 等于产生它的会话标识，可被压实/固化/遗忘按会话归组

#### Scenario: 未归属写入归缺省分组
- **GIVEN** 一次未携带会话标识的 L2 写入
- **WHEN** 条目写入记忆存储
- **THEN** `session_id` 为空串，归入未归属分组（与既有语义兼容，不影响已落账数据）

#### Scenario: 跨层检索
- **GIVEN** 一个查询命中 L1 索引
- **WHEN** 检索器解析索引
- **THEN** 按热度路由到 L2/L3/L4 取详情，而非全库扫描

## ADDED Requirements

### Requirement: 对话转录持久化（非记忆层级）

系统 SHALL 以**按轮追加**（append-only）的方式持久化对话转录：每一条 SHALL 携带 `session_id`、
`role`（`user` / `assistant`）、`content` 与时间戳，落于 `$CORE_STATE_DIR` 下的**单一文件**。
系统 SHALL 支持按 `session_id` 读取该会话转录与取「最近 N 轮」。

转录 SHALL **不是**记忆层级的任何一层（含 L4 —— L4 是遗忘与压实的**归档层**，非对话原文）：
转录条目 SHALL NOT 被 `MemoryStore.read` 返回，SHALL NOT 参与温度分层检索、排名、`reuse_count`
强化、压实、固化与遗忘。转录只能经**按会话的转录读取面**取出。

转录 SHALL 为**单店 + `session_id` 列**（与记忆同店形态一致，不得为每会话建独立存储实例）。

#### Scenario: 追加后可读

- **GIVEN** 某会话一次性追加了若干轮对话
- **WHEN** 另一进程或另一实例按该 `session_id` 读取转录
- **THEN** 读回全部已追加条目，顺序与追加次序一致

#### Scenario: 按会话读取只见本会话

- **GIVEN** 转录中已有 A、B 两个会话的条目
- **WHEN** 以会话 A 的标识读取转录
- **THEN** 返回结果只含 A 的条目

#### Scenario: 反例守门 —— 他人会话转录不可见

- **GIVEN** 转录中已有 A、B 两个会话的条目
- **WHEN** 以会话 B 的标识读取转录
- **THEN** 返回结果**不含** A 的任何条目

#### Scenario: 反例守门 —— 转录不进记忆检索

- **GIVEN** 转录中已有某会话的对话条目
- **WHEN** 经 `MemoryStore.read` 以同一会话标识检索
- **THEN** 检索结果**不含**任何转录条目（转录非记忆层级）

#### Scenario: 文件缺失或坏行降级

- **GIVEN** 转录文件不存在，或其中某一行损坏（非法 JSON）
- **WHEN** 读取转录
- **THEN** 缺失按空转录处理、坏行被跳过，读取不抛错、不阻断主流程
