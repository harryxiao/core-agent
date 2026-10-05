# Evolution Specification

## Purpose
进化引擎实现"进化即结晶"的结晶经济闭环：闭环主干为四阶段——对比诊断（Diagnoser 归因到单个插件）→ 模块级提案（Proposer 生成世代化候选）→ 验证门（Validator 执行 review + 运行时测试）→ 留出评测（Evaluator 防退化）——在此基础上把行动经验结晶为技能/SOP、把无效技能溶解回收，使能力以可复用资产形式沉淀。验证门与留出评测依托可落地的评测基建（基准集 + 评测运行器 + 指标对比基线）工程化执行，并扩展到对任意任务的通用质量评测（任务完成度、正确性、轨迹质量），复用同一套评测基建。

## Requirements

### Requirement: 经验采集
系统 SHALL 从遥测数据中采集"行动→结果"成对证据，作为进化的唯一输入。

#### Scenario: 采集行动结果对
- **GIVEN** 一个任务执行完成
- **WHEN** 进化引擎扫描 trace
- **THEN** 提取 action/result 成对证据，附任务类型与指标

#### Scenario: 无结果证据不采集
- **GIVEN** 一个行动没有可观测结果
- **WHEN** 采集
- **THEN** 跳过，不产生虚假经验

### Requirement: 结晶为技能/SOP
系统 SHALL 把高频成功模式结晶为技能/SOP，并生成带验收标准的单元。

#### Scenario: 生成技能候选
- **GIVEN** 某模式跨 N 个任务成功率达标
- **WHEN** 结晶器运行
- **THEN** 生成技能候选，含 schema/前置条件/验收标准

#### Scenario: 候选待人工确认
- **GIVEN** 一个技能候选生成
- **WHEN** 入库前
- **THEN** 进入评审队列，通过后入 skills 库（与权限审批流联动）

### Requirement: 溶解与回收
系统 SHALL 检测退化的技能/SOP，评估后标记废弃或回收。

#### Scenario: 退化检测
- **GIVEN** 一个技能连续指标退化
- **WHEN** 进化引擎评估
- **THEN** 标记 deprecated，停止路由

#### Scenario: 回收回记忆池
- **GIVEN** 一个技能被判定长期失效
- **WHEN** 溶解器运行
- **THEN** 其有效片段回收为事实/经验，回写记忆层

### Requirement: 对比诊断
系统 SHALL 把缺陷定位到单个插件级别，作为进化闭环的起点；SHALL 接受**可选的目标先验**
（来自课程）作为**并列裁决**输入。

- **先验并入分数、不取代证据**：每条失败证据计 1.0；先验按注入权重（< 1.0）并入同一分数表
  ⇒ 证据恒优先，先验的**唯一**效果是解并列。
- **无先验时行为不变**：仍按「唯一最高分归因，并列则转人工」判定。
- **显式目标不经竞争**：人/宿主显式指定的目标 SHALL 直接作为本轮目标（见「冷路径驱动」），
  不参与本条的分数竞争。

#### Scenario: 归因到插件
- **GIVEN** 一批任务 trace 含失败证据
- **WHEN** Diagnoser 运行诊断
- **THEN** 输出 DiagnosisReport，归因到 target_plugin（None 表示系统级）

#### Scenario: 无插件级归因则人工介入
- **GIVEN** 诊断无法归因到单一插件
- **WHEN** target_plugin 为 None
- **THEN** 转人工处理，不进入提案阶段

#### Scenario: 先验解并列
- **GIVEN** 两个插件各有 1 条失败证据（分数并列），且先验指向其中 A
- **WHEN** 诊断
- **THEN** 归因到 A（无先验时该情形仍转人工）

### Requirement: 模块级提案
系统 SHALL 针对诊断结果生成世代化产物（技能/插件补丁 + delta）。

#### Scenario: 生成候选
- **GIVEN** 一个 DiagnosisReport 已归因到插件
- **WHEN** Proposer 运行
- **THEN** 生成 GenerationCandidate，含 delta 与 kind（skill/plugin）

#### Scenario: 候选进入验证门
- **GIVEN** 候选已生成
- **WHEN** 发布前
- **THEN** 交 Validator 验证，未过门不发布

### Requirement: 验证门
系统 SHALL 对候选执行 review + 运行时测试，通过才允许发布。

#### Scenario: 过门发布
- **GIVEN** 一个候选提交验证
- **WHEN** review 与运行时测试均通过
- **THEN** GateReport.passed=True，候选进入留出评测

#### Scenario: 未过门丢弃
- **GIVEN** 候选未通过验证门
- **WHEN** Validator 判定失败
- **THEN** 丢弃候选，教训写回 L2/L3

### Requirement: 留出评测
系统 SHALL 在留出集上评测候选，防止过拟合与退化。

#### Scenario: 留出集通过则发布
- **GIVEN** 候选通过验证门
- **WHEN** Evaluator 留出集评测不退化
- **THEN** verdict=publish，结晶入库

#### Scenario: 留出集退化回滚
- **GIVEN** 候选在留出集上退化
- **WHEN** Evaluator 判定退化
- **THEN** verdict=rollback，自动回滚并冻结冷却期

#### Scenario: 并发评测资源上限
- **GIVEN** 多个候选同时进入留出评测
- **WHEN** 并发评测请求超过资源配额上限
- **THEN** 超限请求排队或限流，评测资源总量受配额约束，不因并发耗尽资源导致评测结果失真


### Requirement: 评测基建
系统 SHALL 提供可落地的评测基建（基准集 + 评测运行器 + 指标对比基线），支撑验证门与留出评测的工程化执行。

#### Scenario: 基准集注册
- **GIVEN** 一个评测基准（含输入样例与期望指标）准备就绪
- **WHEN** 进化引擎或运维注册该基准
- **THEN** 基准入库并可被留出评测按需引用

#### Scenario: 候选批量评测
- **GIVEN** 一个候选通过验证门
- **WHEN** Evaluator 运行评测
- **THEN** 评测运行器在留出集上批量执行，产出候选指标报告

#### Scenario: 与基线对比判定退化
- **GIVEN** 候选评测指标与当前基线指标均已采集
- **WHEN** Evaluator 对比二者
- **THEN** 不退化则 publish，退化则 rollback，指标差异归档供诊断归因

### Requirement: 任务质量评测
系统 SHALL 对任意任务提供通用质量评测，从任务完成度、正确性、轨迹质量三个维度量化任务执行质量，复用评测基建（基准集 + 评测运行器 + 指标对比基线）工程化执行。

#### Scenario: 任务完成度评测
- **GIVEN** 一个任务执行结束并产出结果
- **WHEN** 评测运行器对任务执行质量评测
- **THEN** 产出完成度指标（目标达成情况），判定任务是否达标

#### Scenario: 正确性评测
- **GIVEN** 一个任务的结果与基准集期望答案
- **WHEN** 评测运行器对比结果与期望
- **THEN** 产出正确性指标（对错或得分），错误归因到失败环节

#### Scenario: 轨迹质量评测
- **GIVEN** 一个任务的完整执行轨迹
- **WHEN** 评测运行器分析轨迹
- **THEN** 产出轨迹质量指标（无效步骤、回退次数等），供诊断与优化

### Requirement: 架构级候选强制人工审批（HITL confirm gate）
系统 SHALL 按风险域区分候选的确认路径：世代化候选 SHALL 携带 `risk_level`（`high` 为架构级——
`kind="plugin"`，`low` 为技能库级——`kind="skill"`）。`risk_level="high"` 的候选 SHALL 强制走
**人工审批**：`confirm` SHALL 要求一张与候选目标一致的**已批准**权限审批单，缺失、未批准或目标
不符时 SHALL NOT 放行（fail-closed，候选保持 `pending`）；`risk_level="low"` 的候选 SHALL 仍须
**显式**人工 `confirm()`——系统 SHALL NOT 提供低风险自动结晶。

- **判定**：`risk_level` SHALL 由提案阶段按 `kind` 判定并随候选固化（不依赖调用方传入）。
- **门禁**：审批判定 SHALL 由 permission 域解释其审批单状态（域外 SHALL NOT 依赖状态字面量）。
- **可追溯**：审批单 SHALL 携带候选目标与 trace，经审批流归档可回溯。
- **拒绝不放行**：被拒/过期/超时的审批单 SHALL NOT 放行候选；`crystallize` 对未确认候选仍 SHALL
  拒绝（既有 `CANDIDATE_PENDING` 语义不变）。

#### Scenario: 架构级候选无审批单不放行
- **GIVEN** 一个 `risk_level="high"` 的候选已过验证门与留出评测
- **WHEN** 不带审批单调用 `confirm`
- **THEN** 抛结构化错误 `CONFIRM_REQUIRED`，候选 `status` 保持 `pending`，`crystallize` 拒绝

#### Scenario: 架构级候选带已批准审批单放行
- **GIVEN** 一个 `risk_level="high"` 的候选，且已有一张目标一致、经人工批准的审批单
- **WHEN** 携带该审批单调用 `confirm`
- **THEN** 候选 `status` 置 `confirmed`，`crystallize` 可发布

#### Scenario: 审批被拒不放过
- **GIVEN** 一个 `risk_level="high"` 的候选，审批单已被人工拒绝
- **WHEN** 携带该审批单调用 `confirm`
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`

#### Scenario: 审批单目标不符不放行
- **GIVEN** 一张已批准但目标为**其他**插件的审批单
- **WHEN** 携带它确认本候选
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`（不得跨候选复用审批）

#### Scenario: 技能级候选仍须显式人工确认
- **GIVEN** 一个 `risk_level="low"` 的候选（`kind="skill"`）
- **WHEN** 调用 `confirm`（不带审批单）
- **THEN** 候选置 `confirmed`（人工确认仍是必要条件，只是不要求权限工单），未被确认时
  `crystallize` 仍拒绝

### Requirement: 观察期回归自动溶解（auto-dissolve）
系统 SHALL 在**结晶发布后**为该产物开启**观察期窗口**（记录发布时评测基线分），并由调用方持续
采样发布后的回归指标：观察样本数达下限**且**观察均分低于「基线 − 容差」时 SHALL **自动溶解**
（技能标 `deprecated`、停止路由，教训 SHALL 写回记忆层并携带回归证据）。溶解后该目标 SHALL 进入
**冻结冷却期**，期内 SHALL NOT 再次触发溶解。

- **开窗**：仅**已发布**（`crystallize` 成功）的产物开窗；未开窗目标的采样 SHALL 被忽略
  （不抛异常，也不累积）。
- **判定**：容差为**绝对分差**（与留出评测的 margin 同一形状）；样本数不足时 SHALL NOT 判定回归。
- **冻结**：冻结期内 SHALL NOT 累积样本、SHALL NOT 触发溶解；冷却期结束 SHALL 自动恢复采样。
- **可追溯**：自动溶解的回归证据（基线 / 观察均分 / 样本数）SHALL 随教训条目留痕。
- 两维度通用：技能级与架构级候选的结晶产物 SHALL 同等开窗。
- **采样来源**：生产侧的采样来源 SHALL 是**冷路径批次指标**——每轮 `run_cycle` 后，对本批 trace
  中**已开窗**的目标按 `plugin_id` 归因计算成功率并各上报一次样本；无归因 trace 的目标
  SHALL NOT 被采样（不产生样本）。

#### Scenario: 回归超阈值自动溶解并保留教训
- **GIVEN** 一个已结晶发布的产物已开窗（基线分 1.0），观察样本达下限且均分低于「基线 − 容差」
- **WHEN** 采样触发判定
- **THEN** 自动 `dissolve`：对应技能标 `deprecated`，教训条目写回记忆层且含基线/均分/样本数

#### Scenario: 冷路径批次指标采样
- **GIVEN** 一个已开窗目标，本批 trace 含归因到该目标 `plugin_id` 的若干条（部分失败）
- **WHEN** 冷路径跑完一轮 cycle 后采样
- **THEN** 该目标被上报一次样本，分数等于本批归因 trace 的成功率

#### Scenario: 无归因 trace 不采样
- **GIVEN** 一个已开窗目标，但本批 trace 无一条归因到该目标
- **WHEN** 冷路径采样
- **THEN** 该目标不被采样（样本数不变）

#### Scenario: 样本不足不判定
- **GIVEN** 观察样本数少于下限（即使单次分数远低于基线）
- **WHEN** 采样
- **THEN** 不判回归、不溶解（仅累积样本）

#### Scenario: 未回归不溶解
- **GIVEN** 观察均分不低于「基线 − 容差」
- **WHEN** 采样达下限
- **THEN** 不溶解，技能保持 `active`

#### Scenario: 冻结期内不再触发
- **GIVEN** 一次自动溶解已发生，目标处于冻结冷却期
- **WHEN** 冷却期内继续采样（即使分数远低于基线）
- **THEN** 不累积样本、不再触发溶解；冷却期结束后恢复采样

#### Scenario: 未开窗目标的采样被忽略
- **GIVEN** 一个从未结晶发布（未开窗）的目标
- **WHEN** 调用采样
- **THEN** 忽略该样本（不抛异常、不建窗、不溶解）

### Requirement: 自动课程（目标生成与调度）

系统 SHALL 提供**课程**：从结构化信号生成**有界、有序**的迭代目标议程（agenda），作为进化冷路径
每一轮的目标选择层，回答「这一轮该迭代谁」。课程 SHALL 由进化引擎侧承担（`CurriculumPlanner`），
SHALL NOT 新增驱动面、SHALL NOT 常驻、SHALL NOT 给模型新增工具。

- **信号面封闭**：SHALL 只使用引擎内部的**结构化数据**——(a) 本批 trace 的失败强度（按
  `plugin_id` 归因计数）；(b) 观察期目标（已发布、观察中）；(c) 待人工确认候选的目标。
  SHALL NOT 读取记忆自由文本、SHALL NOT 调用模型。
- **定序**：主序 = 失败强度**降序**；**降权** = 已处理目标（观察期中 / 已有待确认候选）排在
  未处理目标之后；并列以 `plugin_id` 升序兜底 ⇒ 同一输入**逐项同一**议程（确定性）。
- **预算**：议程长度 SHALL 有上界（默认 3，可注入 `limit`）——「token 有界」在目标选择层的落地。
- **先验而非裁决**：议程 SHALL 只作为**诊断先验**注入（每目标权重 < 1.0）⇒ **证据恒优先、
  先验只破并列**；降权同理**只改并列顺序、不改证据强度**。
- **空信号即空议程**：无失败证据、或失败均无 `plugin_id` 归因线索时，议程 SHALL 为空，
  后续行为与既有路径一致。

#### Scenario: 失败强度定序
- **GIVEN** 本批 trace 含归因到 A 的 3 条失败、归因到 B 的 1 条失败
- **WHEN** 课程生成议程
- **THEN** 议程首项为 A、其次为 B，各自携带失败数作为依据

#### Scenario: 已处理目标降权
- **GIVEN** A 与 B 本批失败数相同，且 A 处于观察期（或已有待确认候选）
- **WHEN** 课程生成议程并注入诊断先验
- **THEN** B 排在 A 之前

#### Scenario: 降权不改证据强度
- **GIVEN** 已被降权的 A 本批有 3 条失败证据，未处理的 B 有 1 条
- **WHEN** 归因
- **THEN** 仍归因到 A（降权只影响并列顺序，不压证据）

#### Scenario: 先验不压证据
- **GIVEN** 先验指向 A，而本批失败证据指向 B（B 失败数 ≥ 1）
- **WHEN** 归因
- **THEN** 归因到 B

#### Scenario: 无信号则议程为空
- **GIVEN** 本批无失败证据，或失败 trace 均无 `plugin_id` 归因线索
- **WHEN** 课程生成议程
- **THEN** 议程为空，诊断不注入任何先验

#### Scenario: 议程有界
- **GIVEN** 本批失败证据覆盖 5 个插件
- **WHEN** 课程生成议程
- **THEN** 议程长度不超过预算（默认 3）

#### Scenario: 议程确定性
- **GIVEN** 同一批 trace 与同一组已处理目标
- **WHEN** 课程连续生成两次议程
- **THEN** 两次结果逐项相同

### Requirement: 冷路径驱动（cold path driving）
系统 SHALL 提供驱动**进化冷路径**的两个入口——①loop 收尾的维护节拍（注入冷路径回调时给出一次机会）
与②CLI 显式入口 `evolve run`——二者 SHALL 调用 `EvolutionWorker.maybe_run`：**是否真正运行一轮
cycle 由 `EvolutionTrigger` 阈值门决定**（显式入口以 `force` 跳过阈值门）；未达阈值 SHALL 不运行
（零额外模型调用、零状态变更）。运行时装配课程后，二者 SHALL 在同一处获得目标选择：

- **阈值门不搬进驱动面**：节拍只提供「机会」，节奏语义仍归 `EvolutionTrigger`。
- **CLI 口径**：`evolve run` SHALL 为一次性动作（装配运行时 → 强制跑一轮冷路径 → 打印结局），
  SHALL NOT 启动常驻进程、SHALL NOT 改变运行态。
- **降级**：驱动失败（回调抛错 / 装配失败）SHALL 降级留痕，SHALL NOT 中断 loop 本轮。
- **自动目标**：未显式指定目标时，`maybe_run` SHALL 用课程议程作为诊断先验；未装配课程时
  SHALL 等价于既有行为（不注入先验）。
- **显式目标**：CLI 入口 SHALL 支持可选 `--goal <plugin_id>`；指定时该目标 SHALL 被**直接采用**
  （不参与归因竞争），且 SHALL 照常走完整四阶段与验证门（发布仍须人工 `confirm`）。
- **红线不变**：驱动面仍只有上述两个；课程 SHALL NOT 新增驱动面 / 常驻进程 / 模型可见工具；
  低风险候选仍须显式人工确认。

#### Scenario: 显式入口强制跑一轮
- **GIVEN** 累积 trace 未达触发阈值
- **WHEN** 执行 `evolve run`
- **THEN** 强制跑一轮 `run_cycle` 并打印结局（诊断/提案或 `no_op`），不启动常驻进程

#### Scenario: 节拍只给机会、阈值门决定
- **GIVEN** 已注入冷路径回调且累积 trace 未达阈值
- **WHEN** loop 收尾维护节拍调用该回调
- **THEN** `maybe_run` 返回 `None`（不运行 cycle、不改状态）

#### Scenario: 显式目标直接采用
- **GIVEN** 本批 trace 的失败证据指向插件 B
- **WHEN** 执行 `evolve run --goal A`
- **THEN** 本轮目标为 A（不被证据改写），照常走提案 → 验证门 → 留出评测

### Requirement: 观察期窗口持久化（observation window persistence）
系统 SHALL 支持把观察期窗口（基线分 / 观察样本 / 冻结截止）落盘为 JSON 并在启动时恢复；
未注入路径时 SHALL 纯内存运行（零行为变化、不写盘）。

- **路径注入**：窗口注册表 SHALL 以**可选路径参数**接收落盘位置（缺省 `None` = 纯内存）。
- **恢复**：以同一路径新建注册表时 SHALL 恢复窗口（含冻结截止——冻结期跨进程仍有效）。
- **降级**：落盘缺失或损坏 SHALL 降级为**无窗口**（不抛异常、不阻断启动）。

#### Scenario: 重启后窗口与冻结期恢复
- **GIVEN** 注册表注入路径，某目标已开窗（含已累积样本与冻结截止）
- **WHEN** 以同路径新建注册表
- **THEN** 该窗口的基线 / 样本 / 冻结截止与落盘前一致

#### Scenario: 未注入路径纯内存
- **GIVEN** 注册表未注入路径
- **WHEN** 开窗 / 采样 / 冻结
- **THEN** 不产生任何落盘文件，行为与未持久化时一致

### Requirement: 人工确认队列的持久化与操作面
系统 SHALL 让进化候选的人工确认队列**可跨进程驱动**：候选 SHALL 携带**稳定身份**（不依赖进程内对象标识），过门候选 SHALL 连同其验证门报告与留出评测报告**作为一条记录**落盘为 JSON 并在启动时恢复；未注入路径时 SHALL 纯内存运行（零行为变化、不写盘）。系统 SHALL 提供操作面以**列出**待确认候选、**确认放行**（确认后即发布结晶）与**拒绝**候选；对 `risk_level="high"` 的候选，操作面 SHALL 作为审批流的**签发端**构造目标一致的权限审批单并经人工批准后再调用 `confirm`。

- **稳定身份**：`GenerationCandidate` SHALL 携带构造即固化、进程内唯一的标识；验证门/留出评测报告的检索 SHALL NOT 依赖 `id(obj)`。
- **随候选留痕**：落盘记录 SHALL 含候选及其门禁与评测结论，使重启后 `confirm` → `crystallize` 仍可判定（不得因重启而误判未过门/退化）。
- **队列语义**：待确认快照 SHALL 只包含 `status="pending"` 的候选；`confirm` 与 `reject` SHALL 落盘并在快照中移除该候选。
- **拒绝语义**：拒绝 SHALL 置候选 `status="rejected"`（可附理由）并落盘；被拒候选 SHALL NOT 可发布。
- **降级**：落盘缺失或损坏 SHALL 降级为**空队列**（不抛异常、不阻断启动）。

#### Scenario: 待确认队列跨进程恢复
- **GIVEN** 一轮冷路径产出过门候选并已落盘
- **WHEN** 以同一路径在新进程中装配引擎
- **THEN** 待确认队列含该候选，且其验证门/留出评测结论一并恢复，可继续确认并发布

#### Scenario: 未注入路径纯内存
- **GIVEN** 引擎未注入落盘路径
- **WHEN** 跑一轮后确认并发布
- **THEN** 不产生任何落盘文件，行为与未持久化时一致

#### Scenario: 操作面列出与确认放行
- **GIVEN** 待确认队列中有一个候选项
- **WHEN** 操作面列出并确认该候选
- **THEN** 候选被放行并发布结晶（结局 `published`），且随即从待确认队列移除

#### Scenario: 操作面拒绝候选
- **GIVEN** 待确认队列中有一个候选项
- **WHEN** 操作面拒绝该候选
- **THEN** 候选置 `rejected` 并从待确认队列移除，后续发布被拒

#### Scenario: 架构级候选的审批单由操作面签发
- **GIVEN** 待确认队列中有一个 `risk_level="high"` 的候选
- **WHEN** 操作面以人工身份确认
- **THEN** 操作面构造目标一致的审批单并经审批流批准后调用 `confirm`，候选被放行

#### Scenario: 候选不存在时的操作面反馈
- **GIVEN** 待确认队列中不含某标识
- **WHEN** 操作面以该标识确认或拒绝
- **THEN** 操作面给出明确反馈并非零退出，队列状态不变
