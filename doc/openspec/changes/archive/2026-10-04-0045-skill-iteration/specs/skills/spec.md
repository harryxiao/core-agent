# Skills Specification Delta

## ADDED Requirements

### Requirement: 技能命中注入（skill hint injection）
系统 SHALL 把**路由命中的技能**以「技能 id + 版本 + `instructions` 节选」注入推理 prompt；
节选 SHALL 有字符上界（token 有界），`instructions` 为空时 SHALL 只注入 id 与版本。

- **载荷**：命中钩子 SHALL 以**纯 dict**（`skill_id` / `version` / `instructions`）交付，供 loop
  渲染——loop SHALL NOT 依赖 skills 类型。
- **口径**：每轮推理前按当轮任务重新路由；未命中或未注入技能库时，prompt SHALL NOT 含技能块。

#### Scenario: 命中技能时注入 id 与步骤
- **GIVEN** 一条 `active` 技能命中当前任务，且其 `instructions` 非空
- **WHEN** 组装推理 system prompt
- **THEN** 技能块含该 `skill_id` 与 `instructions` 节选（超长按上界截断）

#### Scenario: instructions 为空只注入 id
- **GIVEN** 命中技能的 `instructions` 为空
- **WHEN** 组装推理 system prompt
- **THEN** 技能块只含 `skill_id`（不产生空占位行）

### Requirement: 技能执行反馈（skill execution feedback）
系统 SHALL 记录技能的「命中」与「执行结果」，按 `(skill_id, version)` 累计，作为技能迭代的
判据；未注入记录器时 SHALL NOT 记录（零行为变化）。

- **命中**：技能进入 prompt 的那一轮 SHALL 记一次命中。
- **结果**：一轮收尾 SHALL 按该轮实际注入的技能记一次成功/失败（失败含超限终止轮）。
- 反馈 SHALL 仅进程内累积，SHALL NOT 影响本轮推理结果与终止语义。

#### Scenario: 命中与结果按版本累计
- **GIVEN** 一轮任务命中技能 X 且收尾成功
- **WHEN** 记录命中与结果
- **THEN** `(X, 该轮版本)` 命中数 +1、成功数 +1

#### Scenario: 失败轮计入失败
- **GIVEN** 一轮任务命中技能 X 但收尾失败（超限终止）
- **WHEN** 记录结果
- **THEN** `(X, 该轮版本)` 失败数 +1

### Requirement: 技能迭代闭环（skill iteration）
系统 SHALL 在**执行反馈不达标**（样本达下限且失败率达阈值）时触发迭代：由注入的改写器
（DI 可调用，缺省不启用）重写 `instructions` 为新版本并经**灰度发布**生效；两版本样本齐备后
SHALL 以 A/B 对比定夺——提升 SHALL 落地新版本，退化 SHALL 丢弃新版本并保留原版本。

- **触发**：样本数低于下限或失败率低于阈值时 SHALL NOT 迭代；未注入改写器时 SHALL NOT 触发
  （零额外模型调用）。
- **灰度**：新版本 SHALL 仅对按比例抽取的部分任务生效，其余任务仍用原版本。
- **定夺**：A/B 指标 SHALL 取各版本的成功率；胜者 SHALL 成为当前版本（版本号与
  `instructions` 一并落地）；败者 SHALL NOT 改变当前技能，且技能 SHALL NOT 被置
  `status="deprecated"`（退化的是待定版本，不是技能本身）。
- **可逆**：落地新版本 SHALL 登记可逆效应（回滚恢复原版本与原 `instructions`）。

#### Scenario: 反馈不达标触发迭代并灰度
- **GIVEN** 技能 X 失败率达阈值且样本达下限，已注入改写器
- **WHEN** 触发迭代
- **THEN** X 产生新版本草稿（`instructions` 为改写文本）并进入灰度（仅部分任务生效）

#### Scenario: 样本不足不迭代
- **GIVEN** 技能 X 的执行样本少于下限
- **WHEN** 触发迭代
- **THEN** 不产生新版本，且 SHALL NOT 调用改写器

#### Scenario: A/B 提升落地新版本
- **GIVEN** 技能 X 的新版本与当前版本样本齐备，新版本成功率更高
- **WHEN** A/B 定夺
- **THEN** 当前版本号与 `instructions` 更新为新版本

#### Scenario: A/B 退化丢弃新版本
- **GIVEN** 技能 X 的新版本成功率更低
- **WHEN** A/B 定夺
- **THEN** 技能保持原版本与 `instructions`（草稿丢弃），且技能 SHALL NOT 被标记 `deprecated`
