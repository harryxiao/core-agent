# UI Specification Delta

## MODIFIED Requirements

### Requirement: 三模统一内核启动
系统 SHALL 提供 CLI、Web、Desktop 三种启动模式，三者共享同一内核与同一 LLM 配置源；统一后端 API 层 SHALL 以 `create_session` 生成会话标识并**无改写**透传至内核循环与记忆写入（会话归属），`compact(session_id)` SHALL 触发该会话记忆的真实压实，`get_memory(session_id)` SHALL 只返回归属于该会话的记忆条目。

#### Scenario: CLI 直连内核
- **GIVEN** 用户以 CLI 模式启动
- **WHEN** 发起一次会话
- **THEN** 会话通过同一后端 API 层驱动内核 loop，行为与 Web 模式一致

#### Scenario: 会话标识透传至记忆沉淀
- **GIVEN** 用户在某会话（`session_id` 非空）内发起一轮对话
- **WHEN** 内核完成本轮并沉淀记忆
- **THEN** 沉淀条目的 `session_id` 等于该会话标识（API 层透传，不替换、不丢弃）

#### Scenario: 会话记忆按会话读取
- **GIVEN** 存在分属两个会话的记忆条目
- **WHEN** 经 `get_memory(session_id)` 读取其中一个会话
- **THEN** 只返回归属于该会话的条目，其他会话与未归属条目不出现在结果中

#### Scenario: 会话压实
- **GIVEN** 某会话已积累多条 L2 episodic 条目
- **WHEN** 调用 `compact(session_id)`
- **THEN** 触发该会话的压实（存储层按会话聚合与归档语义生效），而非空操作

#### Scenario: 配置单一来源
- **GIVEN** 用户在任一模式配置了 LLM API
- **WHEN** 切换到另一模式
- **THEN** 该配置生效且无需重复配置
