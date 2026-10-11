# Evolution Specification Delta — 结晶通路：真 runner 注入 + 基准人工注册操作面（change 0212）

## MODIFIED Requirements

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
- **执行面语义**：组合根 SHALL 为**生产实际产出的** `task_type` 提供**真实执行器** —— 执行器 SHALL
  以**子 Agent 形状**的循环执行样本输入（会话隔离，SHALL NOT 污染全局记忆层），产出非空计完成度、
  与样本 `expected` 相等计正确性；执行器异常 SHALL **冒泡**给评测器（据此判 `freeze`），
  SHALL NOT 吞成 0 分、SHALL NOT 吞成通过。
- **执行面门控（缺省关）**：真实执行器 SHALL 由一显式开关（`features.evolution_benchmark_runner`，
  缺省**关闭**）控制。关闭 ⇒ SHALL NOT 注入执行器 ⇒ 留出评测 SHALL 与既有实现**逐字一致**地判
  `freeze`（**注册基准 ≠ 同意执行**：注册只是数据入库，注册了基准也不产出留出分、不烧模型调用）。
  理由同 `evolution_executor`：真实执行会调用模型、产生成本，属「关得住、且是关着的」的执行面。
- **注册操作面**：系统 SHALL 提供 CLI 操作面注册基准、设置基线、列清单（`evolve benchmark
  {register|set-baseline|list}`）；该操作面 SHALL 只写**数据面**（与组合根**同源**的单文件落盘），
  SHALL **不装配运行时**（免模型、免凭据），故 SHALL 可在配置不可用时照常读写基准。

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

#### Scenario: 执行面门控关闭时不注入（逐字回到现状）
- **GIVEN** 执行面门控**关闭**（缺省），且基准集里**已有**绑定到某 `target_plugin` 的、含样本的基准，
  并已设置该目标的基线
- **WHEN** Evaluator 评测该目标的候选
- **THEN** 判 `verdict="freeze"`（执行器未注入 ⇒ 无留出分）；行为与**未引入本执行面时逐字一致**，
  SHALL NOT 调用模型、SHALL NOT 产出分数

#### Scenario: 执行面门控开启时经真实执行产出留出分
- **GIVEN** 执行面门控**开启**，基准绑定某 `target_plugin` 且含样本，其 `task_type` 的执行器已注入
- **WHEN** Evaluator 评测该目标的候选
- **THEN** 留出分由**逐样本真实执行**（子 Agent 形状循环、会话隔离）与 `expected` 对比后聚合产出，
  **而非常量缺省值**；产出的分数 SHALL 参与 `publish`/`rollback` 判定（不再 `freeze`）

#### Scenario: CLI 注册面只写数据面且被评测可见
- **GIVEN** 运维经 CLI 在**一次进程**中注册了绑定某 `target_plugin` 的基准并设置其基线（未装配运行时）
- **WHEN** 后续进程构造组合根（同源路径）并评测该目标的候选
- **THEN** 该基准与基线**均可见**（`benchmark_for_plugin` 命中、`baseline_of` 非 `None`）
