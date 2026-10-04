# Skills Specification

## Purpose
技能封装是"记忆即光谱"中 L3 技能段的管理层，负责原子技能库、版本管理与灰度/A/B、技能路由，是"结晶经济闭环"的上半场（下半场为 evolution 的溶解）。

## Requirements

### Requirement: 原子技能库
系统 SHALL 维护原子技能库，每个技能封装为可复用单元，含 schema、前置条件与执行说明。

#### Scenario: 技能注册校验
- **GIVEN** 一个待入库的技能定义
- **WHEN** 其 schema 非法
- **THEN** 拒绝入库并返回 `INVALID_SKILL_SCHEMA`

#### Scenario: 前置条件检查
- **GIVEN** 一个技能的前置条件不满足
- **WHEN** 尝试调用该技能
- **THEN** 调用被拒绝并返回 `PRECONDITION_FAILED`

### Requirement: 版本管理与灰度/A/B
系统 SHALL 支持技能世代版本、灰度发布与 A/B 测试，依据指标决定提升或回退。

#### Scenario: 灰度发布
- **GIVEN** 一个技能发布了新版本
- **WHEN** 新版本仅对部分任务生效
- **THEN** 观察 observability 指标后再决定全量或回退

#### Scenario: A/B 中 B 退化自动回退
- **GIVEN** 技能 A/B 并行测试中 B 指标显著退化
- **WHEN** A/B 对比完成
- **THEN** 自动切回 A，B 标记 deprecated

### Requirement: 技能路由
系统 SHALL 按任务类型自动匹配最合适技能，无匹配时回退通用流程。

#### Scenario: 路由命中 Top-K
- **GIVEN** 一个任务类型
- **WHEN** 路由器匹配技能
- **THEN** 返回匹配度排序的 Top-K 技能

#### Scenario: 路由未命中沉淀
- **GIVEN** 路由器无匹配技能
- **WHEN** 回退通用 loop
- **THEN** 记录未命中，供后续新技能沉淀

### Requirement: 语义路由（semantic routing）
系统 SHALL 在**词法匹配全无命中**时提供语义路由兜底：以注入的语义打分器（缺省不启用）对候选技能
逐条打分，达阈值者按分排序返回；语义命中 SHALL 视为命中（不记未命中）。

- **触发**：仅当词法匹配无任何命中（即原本记 miss 的那条路径）才启用语义；词法命中时 SHALL NOT
  产生模型调用。
- **打分口径**：打分器契约 `(任务文本, 候选技能列表) -> {skill_id: 分值}`；候选 SHALL 只含
  `active`/`gray` 技能。语义分值 SHALL 不低于阈值（缺省 0.5）才被采纳。
- **归组/排序**：命中项按分值降序，返回 Top-K（与词法路径同签名）。
- **降级**：未注入打分器 / 打分器不可用 / 分值低于阈值 → 行为 SHALL 与纯词法一致（返回词法结果，
  无命中则记 miss）；打分器故障 SHALL NOT 中断路由（`match` 不得向调用方抛异常）。

#### Scenario: 词法无命中时语义兜底命中
- **GIVEN** 技能库有 `task_types=["summarize report"]` 的技能，任务文本与任何技能词法不相交
- **WHEN** 注入的语义打分器给该技能打分 0.9（≥ 阈值）
- **THEN** `match` 返回该技能（`score=0.9`），且**不记 miss**

#### Scenario: 词法命中时不走语义
- **GIVEN** 任务文本词法命中某技能
- **WHEN** 调用 `match`
- **THEN** 返回词法结果，且语义打分器**不被调用**

#### Scenario: 未注入打分器时保持词法
- **GIVEN** 未注入语义打分器
- **WHEN** 词法无命中
- **THEN** 返回空列表并记 miss（与既有行为一致）

#### Scenario: 语义分值低于阈值不采纳
- **GIVEN** 词法无命中，语义打分器给全部候选打分均低于阈值
- **WHEN** 调用 `match`
- **THEN** 返回空列表并记 miss

#### Scenario: 打分器不可用时降级为词法
- **GIVEN** 词法无命中，语义打分器整体抛出异常
- **WHEN** 调用 `match`
- **THEN** 不抛出、返回空列表并记 miss（路由不得因打分器故障而中断）

### Requirement: SOP 提炼（skill extraction）
系统 SHALL 提供 SOP 提炼能力：由注入的提炼器（DI 可调用，缺省不启用）把**同一类任务的
成功轨迹**聚合、提炼为一条 `Skill`（`instructions` 承载 SOP 步骤、`task_types` 承载归组键），
并 SHALL 经 `SkillLibrary.register()` 入库（复用既有 schema 校验），入库 SHALL 可逆。

- **触发**：任务**成功**收尾时提交「任务文本 + 行动/结果序列」；失败轨迹 SHALL 不计入累积。
- **阈值**：同一组累计达阈值（缺省 3 条）才提炼一次，提炼后 SHALL 清空该组（下批重新累积）。
- **归组**：SHALL 优先词法命中已有技能的 `task_types` 并复用其作组键；未命中时以任务词元签名
  为新组键。归组口径 SHALL 确定性（离线可断言）。
- **发布**：提炼产物 SHALL 以 `active` 入库（维度1 技能库属低风险自动发布）；提炼文本为空时
  SHALL 不入库。
- 未注入提炼器时 SHALL 不累积、不提炼（零额外调用）；提炼失败 SHALL NOT 中断 Agent 主流程。

#### Scenario: 同类任务达阈值提炼入库
- **GIVEN** 已注入提炼器与技能库，同一类任务成功执行 3 次（阈值）
- **WHEN** 第 3 次成功收尾触发提炼
- **THEN** 技能库新增一条 `Skill`：`instructions` 为提炼文本、`task_types` 含组键、
  `status="active"`；该技能可被 `SkillRouter.match` 命中

#### Scenario: 未达阈值不提炼
- **GIVEN** 同一类任务成功执行次数少于阈值
- **WHEN** 每次成功收尾触发观察
- **THEN** 技能库不新增技能（仅累积样本）

#### Scenario: 失败轨迹不计入累积
- **GIVEN** 同一类任务连续失败（`ok=False`）
- **WHEN** 收尾触发观察
- **THEN** 不累积样本、不提炼（失败轨迹不是 SOP）

#### Scenario: 归组复用已有技能的 task_types
- **GIVEN** 技能库已有一条 `task_types=["report summarize"]` 的技能
- **WHEN** 新任务 "summarize report" 收尾且词法命中该 task_type
- **THEN** 样本归入该 `task_type` 组键（而非新建任务词元签名组）

#### Scenario: 未注入提炼器时降级
- **GIVEN** 未注入提炼器（未配置模型）
- **WHEN** 任务成功收尾
- **THEN** 不累积、不提炼、无额外模型调用，主流程不受影响

#### Scenario: 空提炼不入库
- **GIVEN** 已注入提炼器，样本达阈值
- **WHEN** 提炼返回空文本
- **THEN** 不入库（不写半成品），样本保留待下轮

#### Scenario: 提炼入库可逆
- **GIVEN** 一次提炼已入库一条技能
- **WHEN** 按该次登记的 trace 回滚效应
- **THEN** 技能从库中移除（重复回滚不报错）

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
