# Orchestration Specification Delta

## ADDED Requirements

### Requirement: 难易度感知的调度策略
系统 SHALL 为子任务提供难易度字段 `difficulty`（三档 `easy` / `medium` / `hard`，缺省 `medium`；取值 SHALL 先去除首尾空白并大小写归一，再判集合成员，集合外归一为 `medium`，不抛裸异常、不阻断拆解），并 SHALL 提供**可配置**的同波次调度策略：策略取 `off`（缺省）时，同波次无依赖子任务 SHALL 按依赖拓扑并发扇出（并发度受 `max_concurrency` 上限约束，与引入本策略前**逐字一致**）；策略取 `difficulty` 时，同波次内**存在** `difficulty = hard` 的子任务则该波次 SHALL **串行**执行（按优先级降序逐个），否则维持并发。依赖拓扑 SHALL 仍是**硬约束**（有依赖的子任务必分属不同波次，本策略 SHALL NOT 改变波次划分）。策略取值与并发上限 SHALL 经配置面（ConfigSpec 单一真源）解析，并由**组合根**注入 `TaskScheduler` —— `max_concurrency` SHALL NOT 依赖构造缺省。

#### Scenario: 缺省策略维持既有并发
- **GIVEN** `difficulty_policy` 取缺省 `off`
- **WHEN** 某波次含多个互不依赖的子任务
- **THEN** 该波次并发扇出、并发峰值受 `max_concurrency` 约束，行为与引入本策略前逐字一致

#### Scenario: 难易度策略下含 hard 的波次串行
- **GIVEN** `difficulty_policy` 取 `difficulty`，且某波次含至少一个 `difficulty = hard` 的子任务
- **WHEN** 调度该波次
- **THEN** 该波次串行执行（并发峰值为 1），按优先级降序逐个执行

#### Scenario: 难易度策略下无 hard 的波次并发
- **GIVEN** `difficulty_policy` 取 `difficulty`，且某波次子任务全为 `easy` / `medium`
- **WHEN** 调度该波次
- **THEN** 该波次并发扇出，并发峰值受 `max_concurrency` 约束

#### Scenario: 难易度缺省与非法值归一
- **GIVEN** 子任务未声明 `difficulty`，或模型输出的难易度取值归一后不在三档之内
- **WHEN** 构造子任务
- **THEN** `difficulty` 取 `medium`（归一而非抛错，拆解不因此失败）

#### Scenario: 难易度大小写与空白归一
- **GIVEN** 模型输出 `difficulty` 为 `"HARD"` / `" hard "` / `"Easy"` 等大小写或空白变体
- **WHEN** 构造子任务
- **THEN** 归一为对应小写档位（`hard` / `easy`），而非因字面不等而降级为 `medium`

#### Scenario: 难易度随计划持久化往返
- **GIVEN** 一个含 `difficulty` 的计划被持久化为检查点
- **WHEN** 经 `plan_to_dict` / `plan_from_dict` 往返重建
- **THEN** 每个子任务的 `difficulty` 与持久化前一致（不静默丢字段）；旧检查点缺该字段时回落 `medium`

#### Scenario: 并发上限与策略由配置注入
- **GIVEN** 配置面设置了 `orchestration.max_concurrency` 与 `orchestration.difficulty_policy`
- **WHEN** 组合根装配 `TaskScheduler`
- **THEN** 调度器按配置值执行（非构造缺省）；配置取值非法时校验期阻断启动

## MODIFIED Requirements

### Requirement: 子任务拆解
系统 SHALL 将大目标拆解为带验收标准的分步子任务，按依赖拓扑序执行，并逐步校验。子任务交给子 Agent 执行时
SHALL 携带**发起方会话标识**（可选的 `session_id`，缺省空串 = 未归属），使子任务轨迹按**发起会话**归属
（而非落入全局未归属条目）；空标识时归属语义 SHALL 与既往**逐字一致**。

#### Scenario: 拆解与拓扑执行
- **GIVEN** 一个复杂目标
- **WHEN** 拆解器生成子任务 DAG
- **THEN** 子任务按依赖拓扑序执行，无依赖项可并行

#### Scenario: 子任务轨迹按发起会话归属
- **GIVEN** 一次携带会话标识（非空）的任务派发
- **WHEN** 子 Agent 执行子任务并沉淀轨迹
- **THEN** 轨迹条目的 `session_id` 等于该发起方会话标识

#### Scenario: 未携带会话标识时归属不变
- **GIVEN** 一次未携带会话标识的任务派发
- **WHEN** 子 Agent 执行子任务并沉淀轨迹
- **THEN** 轨迹条目 `session_id` 为空串（归全局层），与既往语义逐字一致

#### Scenario: LLM 拆解产出子任务 DAG
- **GIVEN** 拆解器注入 LLM planner
- **WHEN** 输入一个复合目标
- **THEN** planner 经模型调用产出子任务 DAG（id/goal/acceptance/depends_on/difficulty），按依赖拓扑序与波次执行

#### Scenario: LLM 拆解失败回落单子任务
- **GIVEN** 拆解器注入 LLM planner
- **WHEN** 模型调用失败或输出不可解析为合法子任务集
- **THEN** 回落为单子任务（目标即子任务），任务不因此中断

#### Scenario: 依赖结果交接
- **GIVEN** 子任务 B 依赖子任务 A 且 A 验收通过
- **WHEN** B 开始执行
- **THEN** A 的验收通过结果作为前置上下文注入 B 的执行输入，结果随检查点持久化供续跑重建

#### Scenario: 子任务校验通过才推进
- **GIVEN** 一个子任务执行完成
- **WHEN** 结果未通过其验收标准
- **THEN** 不推进下一步，回退重试（有限次）或重新规划
