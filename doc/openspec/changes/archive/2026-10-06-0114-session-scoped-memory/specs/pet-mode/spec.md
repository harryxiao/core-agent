# Pet-Mode Specification Delta

## MODIFIED Requirements

### Requirement: Pet Session Runtime Wiring
系统 SHALL 经组合根为生产激活的宠物会话注入真实依赖：唤醒用的**组合根装配的真实 loop**
（可为宠物**专属 loop**，非 echo 兜底）、记忆后端、受限探索工具集、安全边界与通知器。
经生产入口激活的宠物 SHALL 因此满足「Preference Tracking」与「Background Pet Session Lifecycle」
需求 —— 偏好落 L2 facts 层，唤醒经真实 loop 执行（而非 echo 兜底）。

「真实 loop」SHALL NOT 被读作「主 loop」：宠物与神兽同型，跑在组合根为其装配的**专属 loop** 上
（`beast-mode` spec 明文「独立 `LoopPlugin` 实例」）—— 专属 loop 才承载受限探索工具集与安全边界，
共享主 loop 会使二者不在路径上（见账本 E29）。

宠物经由该 loop 产生的**执行轨迹** SHALL 以**宠物会话标识**归属（条目 `session_id` 等于宠物会话 id），
SHALL NOT 以未归属（空串）形态落库、SHALL NOT 与主线未归属条目**混同**——宠物是后台自治体，
其轨迹不属于任何前台对话会话。宠物**观察到的主人偏好**（`source=user`）为**刻意知识**，
SHALL 保持全局层（未归属），不随本条归属。

#### Scenario: 生产激活的宠物偏好落 L2
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活一只宠物并观察主人偏好
- **THEN** 偏好以 `MemoryEntry.source=user` 写入运行系统共享的 L2 facts 层（全局层，未归属）

#### Scenario: 生产激活的宠物唤醒走真实 loop
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活的宠物被唤醒
- **THEN** 唤醒经组合根装配的**真实 loop**（宠物专属，非 echo 兜底 loop）执行自治任务

#### Scenario: 宠物轨迹以宠物会话归属
- **GIVEN** 经组合根装配的运行系统，一只宠物被唤醒并跑完一轮自治任务
- **WHEN** 该轮轨迹沉淀进记忆
- **THEN** 条目 `session_id` 等于该宠物会话 id，**不等于**空串，前台会话检索不到它
