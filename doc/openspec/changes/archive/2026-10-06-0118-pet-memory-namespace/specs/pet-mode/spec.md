# Pet Mode Specification Delta

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

宠物经由该 loop 产生的**执行轨迹** SHALL 另落**独立记忆命名空间**（条目 `source=pet`），与主 Agent
（`source=loop`）、神兽（`source=beast.<agent_id>`）三者互不混同——宠物是后台自治体，其自治所得
SHALL NOT 被主 Agent（及神兽）的检索面吸收为自身事实：上述 Agent 的记忆检索面 SHALL **封存**
`pet` 命名空间。该封存 SHALL NOT 使宠物读不到**自身**轨迹：宠物的上下文装配 SHALL 在排除面内
**放行自身**命名空间。本条的命名空间归属与上段的会话归属 SHALL 同时成立、互不替代——会话标识隔离
**会话个体**（哪只宠物），命名空间隔离 **Agent 身份**（宠物 / 神兽 / 主 Agent）。

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

#### Scenario: 宠物轨迹落独立命名空间
- **GIVEN** 经组合根装配的运行系统，一只宠物被唤醒并跑完一轮自治任务
- **WHEN** 该轮轨迹沉淀进记忆
- **THEN** 条目 `source=pet`，与主 Agent（`source=loop`）命名空间隔离

#### Scenario: 主 Agent 检索面封存宠物命名空间
- **GIVEN** 库中已沉淀 `source=pet` 的宠物轨迹（另含主线 `source=loop` 条目）
- **WHEN** 主 Agent 按任务检索（**未带会话标识**，即会话面不过滤）
- **THEN** `source=pet` 条目**不出现**，主线条目**仍出现**

#### Scenario: 宠物自身轨迹可召回
- **GIVEN** 宠物自身已有 `source=pet` 轨迹沉淀，且库中另有 `source=beast.*` 条目
- **WHEN** 该宠物装配上下文并检索
- **THEN** 自身 `source=pet` 条目**出现**（排除面内放行自身命名空间）；`source=beast.*` 条目**不出现**

#### Scenario: 主人偏好不受命名空间封存影响
- **GIVEN** 宠物已观察到主人偏好（`source=user`，全局层）
- **WHEN** 主 Agent 按任务检索
- **THEN** 该偏好条目**仍可出现**（刻意知识，不随宠物命名空间封存）
