# skills spec delta — persist-skills-state

## ADDED Requirements

### Requirement: 技能态持久化（skill state persistence）
系统 SHALL 支持把**技能态**——技能库注册表、执行反馈统计、SOP 样本累积、灰度/A-B 状态——
落盘为 JSON 并在启动时恢复；未注入路径时 SHALL 纯内存运行（零行为变化、不写盘）。

- **路径注入**：各组件 SHALL 以**可选路径参数**接收落盘位置（缺省 `None` = 纯内存）；
  落盘 SHALL NOT 引入第三方依赖（标准库 JSON）。
- **恢复**：以同一路径新建组件时 SHALL 恢复到落盘时的状态（技能含 `version` / `status` /
  `instructions` 等全字段；反馈统计含各 `(skill_id, version)` 计数；样本含各归组键的轨迹；
  灰度/A-B 含待定版本、稳定版本与最近 A/B 结果）。
- **降级**：落盘缺失或损坏（非法 JSON / 结构不符）SHALL 降级为空态并继续运行，
  SHALL NOT 阻断启动、SHALL NOT 抛异常。
- **口径**：持久化 SHALL NOT 改变路由 / 版本选择 / 迭代判定的语义（只跨进程保态）。

#### Scenario: 重启后技能库恢复
- **GIVEN** 技能库注入路径且已注册一条 `active` 技能
- **WHEN** 以同路径新建技能库（模拟进程重启）
- **THEN** 该技能仍在库中，且 `version` / `status` / `instructions` 与落盘前一致

#### Scenario: 重启后反馈统计与灰度/A-B 状态恢复
- **GIVEN** 反馈统计与灰度/A-B 状态注入路径，且已累积计数与发布状态
- **WHEN** 以同路径新建实例
- **THEN** 统计计数与灰度/A-B 状态与落盘前一致

#### Scenario: 重启后 SOP 样本恢复
- **GIVEN** SOP 提炼器注入路径，且某归组键已累积不足阈值的轨迹
- **WHEN** 以同路径新建提炼器并再提交一条同组轨迹
- **THEN** 样本在既有累积上继续计数（达阈值即提炼），不从零重来

#### Scenario: 未注入路径纯内存
- **GIVEN** 组件未注入路径
- **WHEN** 注册技能 / 记录反馈 / 累积样本 / 发布灰度
- **THEN** 不产生任何落盘文件，行为与未持久化时一致

#### Scenario: 落盘损坏降级为空态
- **GIVEN** 路径指向一个非法 JSON 文件
- **WHEN** 以该路径新建组件
- **THEN** 组件以空态启动（不抛异常），后续写入覆盖该文件

## MODIFIED Requirements

### Requirement: 技能执行反馈（skill execution feedback）
系统 SHALL 记录技能的「命中」与「执行结果」，按 `(skill_id, version)` 累计，作为技能迭代的
判据；未注入记录器时 SHALL NOT 记录（零行为变化）。

- **命中**：技能进入 prompt 的那一轮 SHALL 记一次命中。
- **结果**：一轮收尾 SHALL 按该轮实际注入的技能记一次成功/失败（失败含超限终止轮）。
- **累积面**：反馈 SHALL 缺省**仅进程内**累积（不落盘、不写记忆）；注入路径时 SHALL 落盘并在
  启动时恢复（见「技能态持久化」）。反馈 SHALL NOT 影响本轮推理结果与终止语义。

#### Scenario: 命中与结果按版本累计
- **GIVEN** 一轮任务命中技能 X 且收尾成功
- **WHEN** 记录命中与结果
- **THEN** `(X, 该轮版本)` 命中数 +1、成功数 +1

#### Scenario: 失败轮计入失败
- **GIVEN** 一轮任务命中技能 X 但收尾失败（超限终止）
- **WHEN** 记录结果
- **THEN** `(X, 该轮版本)` 失败数 +1
