# Skills Specification Delta — SOP 技能退役（change 0205）

## MODIFIED Requirements

### Requirement: 技能迭代闭环（skill iteration）
系统 SHALL 在**执行反馈不达标**（样本达下限且失败率达阈值）时触发迭代：由注入的改写器
（DI 可调用，缺省不启用）重写 `instructions` 为新版本并经**灰度发布**生效；两版本样本齐备后
SHALL 以 A/B 对比定夺——提升 SHALL 落地新版本，退化 SHALL 丢弃新版本并保留原版本。

- **触发**：样本数低于下限或失败率低于阈值时 SHALL NOT 迭代；未注入改写器时 SHALL NOT 触发
  （零额外模型调用）。
- **灰度**：新版本 SHALL 仅对按比例抽取的部分任务生效，其余任务仍用原版本。
- **定夺**：A/B 指标 SHALL 取各版本的成功率；胜者 SHALL 成为当前版本（版本号与
  `instructions` 一并落地）；败者 SHALL NOT 改变当前技能，且**单次**退化 SHALL NOT 置
  `status="deprecated"`（退化的是待定版本）——**连续**退化的处置见「SOP 技能退役（skill
  retirement）」。
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
- **GIVEN** 技能 X 的新版本成功率更低（**单次**退化）
- **WHEN** A/B 定夺
- **THEN** 技能保持原版本与 `instructions`（草稿丢弃），且技能 SHALL NOT 被标记 `deprecated`

## ADDED Requirements

### Requirement: SOP 技能退役（skill retirement）
系统 SHALL 提供 SOP 技能的**自动退役**路径：在开关 `skills.retirement` 显式开启时，
`SkillIterator` SHALL 逐技能统计**连续** A/B 退化次数——一次退化定义为 A/B 定夺判新版本败且草稿
未采纳，一次提升（新版本落地）SHALL 使该计数归零；计数达阈值 `RETIRE_AFTER_DEGRADATIONS`
（缺省 3）时 SHALL 置该技能 `status="deprecated"`（退役）并登记可逆效应。退役 SHALL 由系统
**自动**判定，SHALL NOT 依赖人工确认。开关缺省**关闭**，关闭时连续退化 SHALL NOT 改变任何技能
的 `status`（逐字回归锚点）。

- **触发**：仅当退化**连续**达阈时 SHALL 退役；中间任一提升 SHALL 归零重计。
- **自动**：退役 SHALL 自动发生，SHALL NOT 需外部确认或人工审批。
- **可逆**：退役 SHALL 登记可逆效应（trace `skills.deprecate`，回滚即恢复退役前 `status`）。
- **退出路由**：退役技能 SHALL 退出路由候选（路由放行集仍只含 `active` / `gray`）。
- **粘性防复活**：已退役技能 SHALL NOT 因**重抽**（同组键再提炼产出同 `skill_id`）被无声复活为
  `active`；复活 SHALL 仅经**显式** `SkillLibrary.activate`。
- **缺省关**：开关未开启时，连续退化 SHALL NOT 改变 `status`，迭代行为逐字不变。

#### Scenario: 连续退化达阈自动退役
- **GIVEN** 开关 `skills.retirement` 已开启，技能 X 连续 3 次 A/B 定夺均判新版本退化
- **WHEN** 第 3 次退化定夺完成
- **THEN** X 的 `status` 置为 `deprecated`

#### Scenario: 一次提升使计数归零
- **GIVEN** 开关 `skills.retirement` 已开启，技能 X 已连续退化 2 次
- **WHEN** 下一次 A/B 定夺判新版本提升（落地）
- **THEN** X 的连续退化计数归零，且 X 的 `status` 保持 `active`（不退役）

#### Scenario: 退役可撤销
- **GIVEN** 技能 X 因连续退化达阈被退役（登记效应 trace `skills.deprecate`）
- **WHEN** 按该 trace 回滚效应
- **THEN** X 的 `status` 恢复为退役前状态

#### Scenario: 缺省关时连续退化不退役
- **GIVEN** 开关 `skills.retirement` **缺省关闭**（未开启），技能 X 连续多次 A/B 定夺均判退化
- **WHEN** 多次退化定夺完成
- **THEN** X 的 `status` 始终保持 `active`（与引入该开关前**逐字一致**）

#### Scenario: 退役技能退出路由候选
- **GIVEN** 技能 X 已退役（`status="deprecated"`）
- **WHEN** 路由匹配任务
- **THEN** X SHALL NOT 出现在路由候选中

#### Scenario: 粘性防复活
- **GIVEN** 一条 SOP 技能已退役（`status="deprecated"`），其归组键对应同一 `skill_id`
- **WHEN** 同一归组键累积成功轨迹再次触发提炼
- **THEN** 该技能 SHALL NOT 被复活为 `active`（仍为 `deprecated`），且本次重抽 SHALL NOT 入库
