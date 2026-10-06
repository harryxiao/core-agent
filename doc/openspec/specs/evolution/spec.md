# Evolution Specification

## Purpose
进化引擎实现"进化即结晶"的结晶经济闭环：闭环主干为四阶段——对比诊断（Diagnoser 归因到单个插件）→ 模块级提案（Proposer 生成世代化候选）→ 验证门（Validator 执行 review + 运行时测试）→ 留出评测（Evaluator 防退化）——在此基础上把行动经验结晶为技能/SOP、把无效技能溶解回收，使能力以可复用资产形式沉淀。验证门与留出评测依托可落地的评测基建（基准集 + 评测运行器 + 指标对比基线）工程化执行，并扩展到对任意任务的通用质量评测（任务完成度、正确性、轨迹质量），复用同一套评测基建。

## Requirements

### Requirement: 经验采集
系统 SHALL 从遥测数据中采集"行动→结果"成对证据，作为进化的唯一输入。采集 SHALL 覆盖**两类**证据来源：①工具调用类（按工具 id 归因）与②**带模块归因**的遥测事件（按事件携带的 `module_id` 归因为该**架构模块**）——后者使架构模块**自身失败**（如执行循环因预算耗尽失败）成为可诊断证据。既有工具调用通道的归因与产出语义 SHALL NOT 改变。①工具调用类通道 SHALL 由**执行循环在生产链路产出**（`kind="tool_call"` 遥测，见 loop「异步流式执行」），SHALL NOT 依赖仅有消费侧而无生产侧的纸面通道。**内部核心模块的 `plugin_id` SHALL 表示「归因对象身份」**（供进化引擎监控该模块与定位其缺陷），**SHALL NOT 蕴含**该模块已纳入 `PluginRegistry` 生命周期；模块自身的失败证据 SHALL 经**模块归因遥测通道**（`module_id`）承载，采集与诊断 SHALL NOT 要求该模块在注册表中可查。

#### Scenario: 采集行动结果对
- **GIVEN** 一个任务执行完成
- **WHEN** 进化引擎扫描 trace
- **THEN** 提取 action/result 成对证据，附任务类型与指标

#### Scenario: 无结果证据不采集
- **GIVEN** 一个行动没有可观测结果
- **WHEN** 采集
- **THEN** 跳过，不产生虚假经验

#### Scenario: 模块失败采集为可归因证据
- **GIVEN** 一个携带模块归因（`module_id`）的失败遥测事件
- **WHEN** 采集
- **THEN** 产出可归因到该模块的证据（`success` 为假），供对比诊断定位到该架构模块

#### Scenario: 既有工具通道归因不变
- **GIVEN** 一个工具调用事件
- **WHEN** 采集
- **THEN** 仍按工具 id 归因并产出工具使用类证据，与既有行为逐字一致

#### Scenario: 工具调用通道在生产有产出
- **GIVEN** 一轮执行经执行循环产出了工具调用遥测（`kind="tool_call"`）
- **WHEN** 采集
- **THEN** 该证据按工具 id 归因为工具使用类，进入提案与诊断回路——通道在**生产**有输入，非仅消费侧就绪

#### Scenario: 内部模块归因不依赖注册表
- **GIVEN** 一个**未纳入** `PluginRegistry` 的内部核心模块（如 `loop.default`）产生了失败证据
- **WHEN** 采集与对比诊断
- **THEN** 仍能归因到该模块 id（证据经模块归因遥测通道承载、并按归因白名单判为架构级候选），不要求该模块在注册表中可查
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
系统 SHALL 针对诊断结果生成世代化产物（技能/插件补丁 + delta）。候选的 `kind` SHALL 由**诊断归因**
驱动：`target_plugin` 属于**内部核心模块**（归因白名单）时 SHALL 产出 `kind="plugin"`，否则 SHALL
产出 `kind="skill"`；`risk_level` SHALL 随 `kind` 固化（`plugin` → `high`，`skill` → `low`）。
提案器 MAY 接受**显式覆盖** `kind`，显式值 SHALL 优先于归因判定。

#### Scenario: 生成候选
- **GIVEN** 一个 DiagnosisReport 已归因到插件
- **WHEN** Proposer 运行
- **THEN** 生成 GenerationCandidate，含 delta 与 kind（skill/plugin）

#### Scenario: 归因到内部核心模块产出架构级候选
- **GIVEN** 一个归因到内部核心模块的 DiagnosisReport（`target_plugin` 属归因白名单，如 `loop.default`）
- **WHEN** Proposer 未收显式 `kind` 覆盖并运行
- **THEN** 候选 `kind` 为 `plugin`、`risk_level` 为 `high`、`status` 保持 `pending`

#### Scenario: 归因到工具产出技能级候选
- **GIVEN** 一个归因到**非**内部核心模块的 DiagnosisReport（如工具 id `tools.file_read`）
- **WHEN** Proposer 未收显式 `kind` 覆盖并运行
- **THEN** 候选 `kind` 为 `skill`、`risk_level` 为 `low`

#### Scenario: 显式覆盖优先于归因
- **GIVEN** Proposer 收显式 `kind="skill"`，而诊断归因到内部核心模块
- **WHEN** 提案
- **THEN** 候选 `kind` 为 `skill`（显式值优先，归因判定被覆盖）

#### Scenario: 候选进入验证门
- **GIVEN** 候选已生成
- **WHEN** 发布前
- **THEN** 交 Validator 验证，未过门不发布

### Requirement: 验证门
系统 SHALL 对候选执行 review + 运行时测试，通过才允许发布。

- **口径版本**：结晶面门 SHALL 带**口径版本**（判定所依据的 review / 运行时测试 / 留出评测口径的
  版本号）；候选 SHALL 在其**提案时**被盖上当时的口径版本并**随候选台账落盘**。投放（`crystallize`）
  时口径与现口径**不符**的候选 SHALL **拒绝**（结构化错误、候选留待确认态，须按现口径**重新提案**），
  SHALL NOT 放行。
- **不重判历史**：口径变更 SHALL NOT 使历史候选**重跑**判定、SHALL NOT 一次性重算历史结论；历史
  候选 SHALL 冻结在**其被记录时**的口径（只有「按现口径重新提案」一条前进路径）。
- **不谎报**：拒绝的理由 SHALL 是「口径不符」，SHALL NOT 表述为「未过 review / 测试」或「留出集
  退化」（那些判定在旧口径下并未发生）。

#### Scenario: 过门发布
- **GIVEN** 一个候选提交验证
- **WHEN** review 与运行时测试均通过
- **THEN** GateReport.passed=True，候选进入留出评测

#### Scenario: 未过门丢弃
- **GIVEN** 候选未通过验证门
- **WHEN** Validator 判定失败
- **THEN** 丢弃候选，教训写回 L2/L3

#### Scenario: 旧口径候选不得投放
- **GIVEN** 一条候选台账记录，其口径版本与现口径不符（含落盘早于口径字段引入的旧记录）
- **WHEN** 该候选已获人工确认并要求结晶投放
- **THEN** 结构化拒绝（口径不符），候选**不发布**、其留待确认态不变；理由 SHALL NOT 记为「退化」

#### Scenario: 现口径候选正常投放
- **GIVEN** 一条候选台账记录，其口径版本等于现口径，且门禁与留出评测结论均通过
- **WHEN** 要求结晶投放
- **THEN** 正常结晶（口径校验不阻断）

### Requirement: 留出评测
系统 SHALL 在留出集上评测候选，防止过拟合与退化。

- **留出分的生产者**：候选的留出分 SHALL 由**已注册基准集的样本**经**基准执行器**逐样本**真实执行**
  后聚合产出；系统 SHALL NOT 以常量、占位值或缺省分充当留出分（否则判定恒为常量、门禁形同虚设）。
- **候选↔基准绑定**：候选 SHALL 经其 `target_plugin` 与基准的**绑定关系**选取留出基准；系统
  SHALL NOT 回落到「任意一个基准」或「与被评对象同源的基准」。
- **无法评测 ⇒ 冻结（fail-closed）**：候选**无绑定基准**、基准**无样本**、或基准**执行器未注册**时，
  系统 SHALL 判**无法评测**并给 `verdict="freeze"`（候选不下发、不发布）；SHALL NOT 报 `publish`，
  SHALL NOT 报 `rollback`（无退化证据 —— 「无法评测」不得被谎报为「退化」）。
- **阈值口径**：退化判定 SHALL 把**已注册的基线分**当作**绝对阈值**（`held_out < baseline` 即退化）；
  未注册基线 SHALL NOT 被静默当作 `0.0` 的「宽松阈值」放行（无基线即无对比面 ⇒ 归入「无法评测」）。

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

#### Scenario: 留出分由基准执行器真实产出
- **GIVEN** 一个候选，其 `target_plugin` 绑定了含样本的基准，且该基准 `task_type` 的执行器已注册
- **WHEN** Evaluator 评测该候选
- **THEN** 留出分等于**逐样本真实执行**结果与期望对比后的聚合分（而非常量缺省值）

#### Scenario: 无法评测则冻结
- **GIVEN** 一个候选，其 `target_plugin` **无**绑定基准（或基准无样本、或执行器未注册）
- **WHEN** Evaluator 评测该候选
- **THEN** `verdict="freeze"`、`passed=False`；候选**不发布**、**不**被记作退化、**不**触发回滚

### Requirement: 评测基建
系统 SHALL 提供可落地的评测基建（基准集 + 评测运行器 + 指标对比基线），支撑验证门与留出评测的工程化执行。

- **落盘**：基准集与基线 SHALL 持久化于 `$CORE_STATE_DIR` 下**单文件**（跨进程可读）——注册基准、
  设置基线 SHALL 落盘，后续进程（CLI 每条命令各起一份装配）SHALL 读得同一份基准集与基线。
- **人工注册面**：基准 SHALL 可由**人工/运维**注册（含输入样例与期望指标）并为其目标设置基线；
  系统 SHALL NOT 以**被评对象的自身历史分**充当基线（自证）。
- **执行面注入**：基准样本的**执行器**（按 `task_type` 映射到可调用体）SHALL 由**组合根或运维注入**；
  执行器 SHALL NOT 随基准集落盘（**数据面与执行面分离**：数据面可被人工注册，执行面必须由受信代码提供）。
- **降级告警**：落盘缺失 SHALL 表现为空基准集（不阻断启动）；落盘**损坏/结构不符** SHALL 降级为空
  基准集并**告警**，SHALL NOT 静默吞掉。
- **无副作用声明**：基准确立 SHALL **不**改任何被评对象的运行时行为（注册只是数据入库）。

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

#### Scenario: 基准集跨进程可读
- **GIVEN** 一次进程中注册了基准并设置了基线（已落盘），该进程退出
- **WHEN** 后续进程构造基准注册表
- **THEN** 读回同一份基准集与基线（`list()` 与基线分一致）

#### Scenario: 基准集损坏降级并告警
- **GIVEN** 落盘的基准集文件内容损坏（非法 JSON / 结构不符）
- **WHEN** 构造基准注册表
- **THEN** 降级为空基准集、**告警**留痕、**不抛异常**、不阻断启动

#### Scenario: 执行器未注册不谎报
- **GIVEN** 基准已注册但对应 `task_type` 的执行器未由组合根/运维注入
- **WHEN** 留出评测试图评测
- **THEN** 判**无法评测**（不产出分数、不判通过），SHALL NOT 以缺省分放行

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
- **结局诚实**：架构级候选获批并过门后 SHALL 以 `accepted` 结局登记（语义为「已批准、**待人工
  实施**」）——**未启用原生执行器时**，系统 SHALL NOT 在该分支报告 `published`（无架构产物被发布、
  无世代被晋升）。**启用原生执行器时**，该分支的结局口径 SHALL 遵守「架构级候选的原生实施
  （可选）」Requirement：`accepted` 仍 SHALL 为**实施筹备的前置登记结局**，实施 SHALL 由**独立的**
  操作面另行驱动、并**额外**经验证门与人工复核，SHALL NOT 因此免去本 Requirement 的任何一道人工关，
  亦 SHALL NOT 使本方法（`crystallize`）的返回值改变。
  技能级候选 SHALL 以 `published` 结局登记（确实写入技能库）。两个分支 SHALL 同样开启观察期
  （观察期判的是「批准之后是否回归」，与是否有产物无关）。

#### Scenario: 架构级候选无审批单不放行
- **GIVEN** 一个 `risk_level="high"` 的候选已过验证门与留出评测
- **WHEN** 不带审批单调用 `confirm`
- **THEN** 抛结构化错误 `CONFIRM_REQUIRED`，候选 `status` 保持 `pending`，`crystallize` 拒绝

#### Scenario: 架构级候选带已批准审批单放行
- **GIVEN** 一个 `risk_level="high"` 的候选，且已有一张目标一致、经人工批准的审批单
- **WHEN** 携带该审批单调用 `confirm`，随后 `crystallize`
- **THEN** 候选 `status` 置 `confirmed`，结晶结局为 **`accepted`**（「已批准、待人工实施」，
  **不**报 `published`）——**与原条款逐字一致**（原生执行器是否启用**不改变**本返回值），
  并开启观察期

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

#### Scenario: 技能级候选结晶报 published
- **GIVEN** 一个已确认、过验证门、留出集不退化的 `risk_level="low"` 候选
- **WHEN** `crystallize`
- **THEN** 技能写入技能库且结局为 `published`

#### Scenario: 未确认候选不产出任何发布类结局
- **GIVEN** 一个 `status="pending"` 的候选（无论 `risk_level`）
- **WHEN** 直接调用 `crystallize`
- **THEN** 抛 `CANDIDATE_PENDING`，不产生 `accepted` 亦不产生 `published` 结局

### Requirement: 架构级候选的原生实施（可选）
系统 SHALL 支持把架构级候选的 `accepted` 结局**可选地**推进为**已实施**：**仅当**
`features.evolution_executor` 显式开启时，组合根 SHALL 装配**原生执行器**（`EvolutionExecutor`）；
未声明（**缺省**）时 SHALL NOT 装配——关时不构造实例、不产生装配期副作用，`accepted` 结局逐字
回到本 Requirement 引入前的现状，且 `crystallize` 的返回值在任何情况下 SHALL 不变（恒为 `accepted`）。

执行器 SHALL **仅由操作面显式驱动**（`core-agent evolve implement …`），SHALL NOT 挂进 loop 的
热/冷路径节拍、SHALL NOT 注册为任何 Agent 可调用的工具。实施 SHALL 分**两阶段**，**复核前
SHALL NOT 落地**：

- **筹备（prepare，`--dry-run`）**：由**补丁生产者**按候选产出补丁 → **范围守卫** → 应用 →
  跑**冻结验证门** → **回退**。制品（补丁内容、被改文件的原内容、各门禁结论）SHALL 落入**候选台账**
  （与候选同一条记录承载，跨进程可读），SHALL NOT 在本阶段留下任何工作树改动。
- **复核（review）**：制品 SHALL 以**可复核的形式**（补丁差异 + 门禁报告）呈现给人工，并 SHALL
  经人工**复核关**——要求一张与候选目标一致的**已批准**审批单，其操作标识 SHALL 与 `confirm` 阶段
  的审批单**可区分**（不得跨阶段复用同一张单）；缺失、未批准或目标不符时 SHALL NOT 落地（fail-closed）。
- **落地（commit）**：复核通过后 SHALL 应用**被复核的那一份**制品（SHALL NOT 重新产出补丁），
  记录**可逆效应**（undo 可回退），候选状态与结局 SHALL 为 **`implemented`**
  （`EvolutionOutcome.status` 的**新增**词表项）；`accepted` 的「已批准、未实施」诚实语义 SHALL NOT
  被回退为 `published`。

约束：

- **门禁独立性**：门禁命令 SHALL 取自**单一真源**（`GATE_COMMANDS`），执行器 SHALL NOT 自选门禁
  命令、SHALL NOT 另立第二份门禁清单；门禁 SHALL 经**独立执行面**（子进程）运行。留出评测
  （`Evaluator`）**不**参与实施验证——本 Requirement 只承诺冻结门。
- **范围守卫**：补丁路径 SHALL 限于**源码面**（`src/core/` 内的 `.py`），且 SHALL NOT 触碰验证装置
  与信任链（测试与测试配置、构建/类型/风格配置、门禁命令真源、权限审批、配置开关、进化引擎与
  台账、组合根与操作面、规格与变更目录、CI 配置）；触碰即 SHALL 拒绝且 SHALL NOT 应用。
- **路径与归因一致**：补丁路径 SHALL 由候选的**归因目标**（`target_plugin`，须为内部核心模块 id）
  经**约定**解析得出且该文件**确实存在**；不符或不存在时 SHALL 拒绝（fail-closed，不应用）。
- **可逆**：落地 SHALL 记录可逆效应（`EffectTracker.record(effect, undo)`）；筹备阶段的临时应用
  SHALL 在门禁跑完后被回退。
- **崩溃安全**：被改文件的原内容 SHALL 在**应用之前**随制品持久化，且回退 SHALL 在异常路径下
  同样完成（`finally` 语境）。
- **漂移拒绝**：落地前 SHALL 校验目标文件当前内容与筹备时记录的原内容**一致**，不一致 SHALL
  结构化拒绝（`IMPLEMENT_STALE`）且不落地。
- **不进入运行**：补丁 SHALL NOT 在通过验证门与人工复核之前成为运行系统的行为（对齐 `CORE-EVO-R3`）。
- **观察期开窗口径不变**：开窗仍发生在 `crystallize` 返回 `accepted` 之时，实施 SHALL NOT 重复开窗。

#### Scenario: 开启执行器时筹备并落 implemented
- **GIVEN** `features.evolution_executor` 显式开启，一个架构级候选已 `accepted`，补丁通过范围守卫与
  归因一致性校验、且全部门禁通过，并已获一张目标一致、已批准的实施复核单
- **WHEN** 先筹备（`--dry-run`）再复核落地
- **THEN** 补丁被永久应用、记录可逆效应、候选状态与结局为 **`implemented`**（不是 `accepted`、
  不是 `published`）

#### Scenario: 缺省不装配执行器（逐字回到现状）
- **GIVEN** `features.evolution_executor` 未声明（缺省）
- **WHEN** 系统启动装配，且一个架构级候选走到 `crystallize`
- **THEN** 不装配执行器（装配面为空）、不产生装配期副作用；结局仍为 `accepted`，操作面拒绝执行
  并说明原因，且不产生任何 `implemented`

#### Scenario: 门禁不过则回退不落地
- **GIVEN** 执行器已开启，补丁已应用且**未**通过冻结验证门（任一门禁失败）
- **WHEN** 筹备结束
- **THEN** 临时应用 SHALL 被回退（工作区恢复筹备前状态），SHALL NOT 留下制品、SHALL NOT 落
  `implemented`，并抛出结构化门禁失败

#### Scenario: 补丁触碰验证装置被范围守卫拒绝
- **GIVEN** 执行器已开启，补丁生产者产出的补丁路径落在验证装置或信任链内（如测试目录、测试/
  构建配置、门禁命令真源、权限审批、配置开关、规格目录）
- **WHEN** 筹备执行范围守卫
- **THEN** 结构化拒绝该补丁，**不应用**任何改动（工作区逐字不变）、不落 `implemented`

#### Scenario: 补丁路径与候选归因不符被拒绝
- **GIVEN** 执行器已开启，补丁生产者为归因到内部核心模块 A 的候选给出了指向**另一个**模块文件
  （或指向一个**不存在**的文件）的路径
- **WHEN** 筹备校验路径与归因一致性
- **THEN** 结构化拒绝，**不应用**任何改动、不落 `implemented`

#### Scenario: 落地前须先有已筹备制品
- **GIVEN** 执行器已开启，一个已 `accepted` 的架构级候选**尚未**筹备
- **WHEN** 直接要求落地（未先 `--dry-run`）
- **THEN** 结构化拒绝并提示先筹备，**不应用**任何改动、不落 `implemented`

#### Scenario: 复核单缺失或目标不符不放行
- **GIVEN** 一个已筹备待复核的架构级候选
- **WHEN** 不带审批单、或携带非已批准、或携带目标为其他插件、或携带 `confirm` 阶段那张
  （操作标识不可区分）的单子要求落地
- **THEN** 抛 `CONFIRM_REQUIRED`，**不落地**（工作区逐字不变）、不落 `implemented`，候选仍待复核

#### Scenario: 落地前工作区漂移则拒绝
- **GIVEN** 一份已筹备待复核的制品，且其目标文件在筹备之后被外部改动（与筹备时记录的原内容不一致）
- **WHEN** 要求落地
- **THEN** 结构化拒绝（`IMPLEMENT_STALE`），**不落地**，避免把补丁覆盖到已漂移的内容上

#### Scenario: 落地后可跨进程查得已实施状态
- **GIVEN** 一次成功的落地已发生（操作面进程已退出）
- **WHEN** 后续进程查该候选
- **THEN** 候选状态为 `implemented`、制品（补丁与门禁报告）仍可读——实施结论 SHALL NOT 只存在于
  一次性进程的标准输出

### Requirement: 观察期回归自动溶解（auto-dissolve）
系统 SHALL 在**结晶发布后**为该产物开启**观察期窗口**（记录发布时评测基线分），并由调用方持续
采样发布后的回归指标：观察样本数达下限**且**观察均分低于「基线 − 容差」时 SHALL **自动溶解**
（技能标 `deprecated`、停止路由，教训 SHALL 写回记忆层并携带回归证据）。溶解后该目标 SHALL 进入
**冻结冷却期**，期内 SHALL NOT 再次触发溶解。

- **开窗**：仅**结晶成功**（`crystallize` 返回 `published` 或 `accepted`）的产物开窗；未开窗目标的
  采样 SHALL 被忽略（不抛异常，也不累积）。
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
