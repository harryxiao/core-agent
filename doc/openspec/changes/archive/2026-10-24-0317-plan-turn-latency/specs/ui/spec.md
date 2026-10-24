# Spec Delta — ui（0317 计划拆解的等待上界）

## ADDED Requirements

### Requirement: 计划拆解的等待上界

计划轮进入拆解阶段后，等待拆解结果的时长 SHALL **有界**。缺省上界 SHALL 为主 LLM 单次调用
超时 + 30 秒余量（未注入 LLM 配置时为 90 秒）；该上界 SHALL 可由**装配参数**覆盖（供测试与
嵌入式装配使用），SHALL NOT 新增面向用户的配置键。

拆解在**上界内**返回时，语义与既有「会话级执行模式与计划审批」逐字一致（正常产出
`plan.draft_ready`）。超时 SHALL 返回 `UI_PLAN_DRAFT_FAILED`，回执 SHALL 明示实际上界与
「重试或改用 /quick」指引；SHALL NOT 产出 `plan.draft_ready`、SHALL NOT 创建草案、SHALL NOT
静默回落为单子任务、SHALL NOT 无限等待。超时后的会话模式与草案状态 SHALL 与拆解失败一致
（不残留半成品草案）。

#### Scenario: 拆解超时快速失败
- **GIVEN** 拆解调用挂起超过上界
- **WHEN** 计划轮进入拆解阶段
- **THEN** 在上界附近返回 `UI_PLAN_DRAFT_FAILED`（文案含上界与 `/quick`），无 `plan.draft_ready`
  事件、无待决草案，会话模式不变

#### Scenario: 上界内返回语义不变
- **GIVEN** 拆解调用在上界内正常返回
- **WHEN** 计划轮进入拆解阶段
- **THEN** 先产出 `plan.drafting`、再产出 `plan.draft_ready`，草案内容与既有语义一致

#### Scenario: 缺省上界随 LLM 超时推导
- **GIVEN** 未显式指定拆解上界、已注入单次超时为 T 的 LLM 配置
- **WHEN** 装配计划轮
- **THEN** 拆解上界为 T + 30 秒；未注入 LLM 配置时为 90 秒
