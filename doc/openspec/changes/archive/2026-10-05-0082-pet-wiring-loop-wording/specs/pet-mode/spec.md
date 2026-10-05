# pet-mode spec delta — 「Runtime Wiring」的 loop 措辞订正

**把规格字面「主 loop」订正为「组合根装配的真实 loop（可为专属 loop）」。**

`0081` 起宠物跑在**专属 loop**（受限工具集 + 安全中间件）上 —— 这是用户裁决「专属 loop 真强制」的
必然结果（共享主 loop 会使 R11 受限工具集与 R12 安全边界**都不在路径上**）。规格原字面「唤醒用的主 loop」
遂成陈迹。本 delta 只订正措辞，**不改行为类条款**。

对照：`beast-mode` spec 明文「神兽以独立 `LoopPlugin` 实例运行」⇒ 「真实 loop ≠ 主 loop」是本仓既定语义，
pet 那句「主 loop」是**措辞孤例**（change `0081` 自报，账本 E29）。

## MODIFIED Requirements

### Requirement: Pet Session Runtime Wiring
系统 SHALL 经组合根为生产激活的宠物会话注入真实依赖：唤醒用的**组合根装配的真实 loop**
（可为宠物**专属 loop**，非 echo 兜底）、记忆后端、受限探索工具集、安全边界与通知器。
经生产入口激活的宠物 SHALL 因此满足「Preference Tracking」与「Background Pet Session Lifecycle」
需求 —— 偏好落 L2 facts 层，唤醒经真实 loop 执行（而非 echo 兜底）。

「真实 loop」SHALL NOT 被读作「主 loop」：宠物与神兽同型，跑在组合根为其装配的**专属 loop** 上
（`beast-mode` spec 明文「独立 `LoopPlugin` 实例」）—— 专属 loop 才承载受限探索工具集与安全边界，
共享主 loop 会使二者不在路径上（见账本 E29）。

#### Scenario: 生产激活的宠物偏好落 L2
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活一只宠物并观察主人偏好
- **THEN** 偏好以 `MemoryEntry.source=user` 写入运行系统共享的 L2 facts 层

#### Scenario: 生产激活的宠物唤醒走真实 loop
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活的宠物被唤醒
- **THEN** 唤醒经组合根装配的**真实 loop**（宠物专属，非 echo 兜底 loop）执行自治任务
