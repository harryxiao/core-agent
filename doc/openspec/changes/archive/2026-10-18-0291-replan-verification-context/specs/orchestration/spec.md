# orchestration — 任务级验收反馈闭环（change 0291）

## MODIFIED Requirements

### Requirement: 子任务拆解
系统 SHALL 将大目标拆解为带验收标准的分步子任务，按依赖拓扑序执行，并逐步校验。子任务交给子 Agent 执行时
SHALL 携带**发起方会话标识**（可选的 `session_id`，缺省空串 = 未归属），使子任务轨迹按**发起会话**归属
（而非落入全局未归属条目）；空标识时归属语义 SHALL 与既往**逐字一致**。

子任务验收失败 SHALL 进入**有限恢复回路**：先仅对**失败子任务**重试一次（已完成子任务 SHALL NOT
重跑），仍失败则**重新拆解一次**（保留原目标与已定成功标准；新计划 SHALL 清空旧计划的完成集与
结果上下文，避免子任务 id 复用导致误跳过或脏依赖）；恢复预算耗尽 SHALL 转 `FAILED`，错误码
沿用最后一次失败原因。子 Agent 执行抛出结构化异常 SHALL 归一为子任务失败并进入同一恢复回路，
SHALL NOT 让异常穿透调度器。空计划（无任何子任务）SHALL 判失败，SHALL NOT 以「空标准视为通过」
误判 `DONE`。

重新拆解输入 SHALL 在字符预算内携带**任务级失败上下文**：任务级判定未通过时，输入 SHALL 以
判定器给出的失败原因与**全部任务级成功标准**开头，失败段与标准 SHALL 各自有界，且二者 SHALL
优先于已完成列表与原始目标（原始目标 SHALL 有界）——保证总截断后失败段仍存活。子任务失败 /
死循环分支的输入内容与顺序 SHALL 保持不变。重新拆解回执中任一子任务的 `goal`（去空白）**精确
等于**重拆输入（去空白）SHALL 视为回执退化并判 `FAILED`（`SUBTASK_VERIFY_FAILED`），SHALL NOT
执行该回执中的任何子任务；该守卫 SHALL 只作用于重新拆解，初次拆解的离线回落语义 SHALL 不变。

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

#### Scenario: 重试只重跑失败子任务
- **GIVEN** 一波次内子任务 A 验收通过、子任务 B 验收失败
- **WHEN** 调度器进入重试
- **THEN** 仅 B 被重新执行一次（`subtask_started` 携带 `attempt=2`），A 不被重跑

#### Scenario: 重试通过后继续推进
- **GIVEN** 子任务首次验收失败
- **WHEN** 重试后验收通过
- **THEN** 该子任务记录完成，任务继续推进并最终可达 `DONE`（`replans=0`）

#### Scenario: 重试仍失败触发重新拆解
- **GIVEN** 子任务首次与重试均未通过验收
- **WHEN** 恢复回路仍有重新拆解预算
- **THEN** 任务转入 `RECOVERING`，以原目标、已完成摘要与失败原因重新拆解一次后重入执行

#### Scenario: 恢复预算耗尽转 FAILED
- **GIVEN** 重试与重新拆解预算均已用尽
- **WHEN** 子任务仍未通过验收或目标仍未达成
- **THEN** 任务转 `FAILED`，`task_failed` 携带最后一次失败原因与 `attempts` / `replans` 计数

#### Scenario: 执行异常归一为子任务失败
- **GIVEN** 子 Agent 执行抛出结构化异常
- **WHEN** fan-out 回收结果
- **THEN** 该子任务归一为失败（保留结构化错误码），进入同一重试/重拆回路，异常不穿透调度器

#### Scenario: 空计划不误判完成
- **GIVEN** 检查点或 planner 产出不含任何子任务的计划
- **WHEN** 调度器开始执行
- **THEN** 任务判 `FAILED`（`task_failed`），不因「空成功标准视为通过」而判 `DONE`

#### Scenario: 重新拆解输入携带任务级失败上下文
- **GIVEN** 全部子任务均通过验收，但任务级判定未通过（`PROGRESS_NOT_MET`），且计划带有成功标准
- **WHEN** 调度器触发重新拆解
- **THEN** 重拆输入包含判定器给出的失败原因与全部任务级成功标准，二者位于「已完成子任务」
  之前；即使原始目标超长（超过单段字符上界），失败原因与标准仍保留在输入内

#### Scenario: 重新拆解回执退化为原输入
- **GIVEN** 重新拆解请求已发出，planner 返单一子任务且其 `goal`（去空白）等于重拆输入（去空白），
  或返多个子任务其中任一 `goal` 如此
- **WHEN** 调度器收到该回执
- **THEN** 任务判 `FAILED`（`SUBTASK_VERIFY_FAILED`，携带 `replans` 计数），该回执中的子任务
  SHALL NOT 被执行（执行器调用次数不增加）

### Requirement: 多 Agent 协同
系统 SHALL 支持按任务类型路由到最合适的子 Agent，并通过标准化消息协议完成交接。
交接 SHALL 使用统一执行框架：调度器、beast、pet 三条执行路径 SHALL 复用同一份
`TaskHandoff` 渲染与执行实现；`task` / `context_pack` / `acceptance` / `deadline` /
`priority` / `session_id` 六个字段 SHALL 全部被消费。

`context_pack` SHALL 由交接前置信息构建且**有界**：总预算按粗略 token 估算（CJK 感知），
单字段另有字符上界；预算耗尽时 SHALL 停止装入后续依赖，SHALL NOT 无界拼接。

`deadline` 语义为**秒为单位的时长**（`None` 或 `<=0` = 不设限）；设限时 SHALL 在超时后
取消子 Agent 执行流，并把该子任务归一为失败（错误码 `SUBTASK_TIMEOUT`），SHALL NOT
让任务无限挂起。`session_id` SHALL 原样转交子 Agent 执行（空串 = 未归属），
会话命名空间隔离语义 SHALL 保持不变。

`acceptance` SHALL 由子任务自身验收标准与**非空的任务级成功标准**组合而成，任务级标准 SHALL
以明确标题区分，组合结果整体 SHALL 有界（不超过交接字符上界）；无任务级标准时 `acceptance`
SHALL 与既往逐字一致。子任务级验收语义 SHALL 仍只依据子任务自身 `acceptance`，任务级标准
SHALL NOT 改变子任务验收判定。

#### Scenario: 能力匹配与交接
- **GIVEN** 一个子任务需要特定能力
- **WHEN** 路由器匹配到合适的子 Agent
- **THEN** 通过 TaskHandoff 交接，交接上下文由 context 模块打包

#### Scenario: 无匹配 Agent
- **GIVEN** 没有子 Agent 能处理当前子任务，且无可用 fallback
- **WHEN** 路由器打分无命中
- **THEN** 抛出 NO_AGENT_MATCH，调度器捕获并标记子任务失败

#### Scenario: 交接全字段被消费
- **GIVEN** 调度器执行一个带依赖、验收标准、优先级与会话标识的子任务
- **WHEN** 子 Agent 收到交接
- **THEN** 执行输入包含原始目标、前置子任务结果与验收标准；TaskHandoff 携带的
  deadline / priority / session_id 与子任务一致

#### Scenario: 交接上下文有界
- **GIVEN** 前置子任务结果总长超过上下文预算
- **WHEN** 构建 context_pack
- **THEN** 包内文本按依赖顺序装入并在预算耗尽处截断，单字段不超过字符上界，
  不会无界拼接全部结果

#### Scenario: 交接超时归一为失败
- **GIVEN** 子任务的 deadline 已设且子 Agent 执行超过该时长
- **WHEN** 执行流被超时取消
- **THEN** 该子任务以 `SUBTASK_TIMEOUT` 失败并进入既有恢复回路，任务不无限挂起

#### Scenario: 三条执行路径复用统一执行器
- **GIVEN** beast / pet 的交接上下文为空且未设验收标准
- **WHEN** 经统一执行器执行
- **THEN** 子 Agent 收到的 prompt 与交接前的任务文本逐字相同，会话标识与执行单元不变

#### Scenario: 交接携带任务级成功标准
- **GIVEN** 计划带有非空的任务级成功标准，且子任务自身有（或没有）验收标准
- **WHEN** 调度器构造该子任务的交接
- **THEN** 交接的 `acceptance` 含任务级标准清单且整体不超过字符上界；执行者首轮 prompt
  即可见该清单；子任务验收判定仍只依据其自身验收标准；无任务级标准时 `acceptance`
  与既往逐字一致

### Requirement: 目标监控
系统 SHALL 用 Goal 与 SuccessCriteria 定义任务级成功标准，并由 ProgressTracker 追踪每子任务
进度与整体目标推进，进度未达标时触发重试或重规划。

成功标准 SHALL 默认由拆解器在拆解时生成（顶层 `success_criteria`，2-5 条、每条可客观判定
真伪、覆盖整体目标而不复述子任务 acceptance）；调用方显式提供的非空标准 SHALL 优先于生成
标准；拆解失败回落的单子任务计划 SHALL NOT 自带标准（同源判定 fail-closed 不得把任务拖死）。
重新拆解时原标准非空 SHALL 保留。

任务终态 SHALL 由任务级判定器对照 Goal + SuccessCriteria + 子任务结果判定；未注入判定器而
存在标准时 SHALL 以 `MISSING_SUCCESS_CHECKER` 失败（fail-fast）；判定器异常或返回非法结果
SHALL fail-closed（判未达标），SHALL NOT 裸崩或静默放行。未达标 SHALL 进入恢复回路：重拆
预算未用尽则重新拆解，否则任务判 `FAILED`。

任务级判定未通过时，进入重新拆解前的输入 SHALL 携带判定器给出的原因与全部任务级成功标准
（各自有界），使重拆能够针对差距补充子任务；重拆输入 SHALL NOT 只携带原目标与已完成列表。

ProgressTracker SHALL 维护每子任务的三态进度：已开始（`started`）、已完成（`completed`）、
失败待恢复（`failed`）；重试开始与完成 SHALL 清除失败标记，重新拆解 SHALL 清空三态。

#### Scenario: 成功标准定义
- **GIVEN** 任务进入拆解且调用方未显式提供成功标准
- **WHEN** planner 产出拆解结果
- **THEN** 计划的 success_criteria 取自 planner 生成的标准（去空白、去重、至多 5 条），
  标准可判定真伪、可度量（SMART）

#### Scenario: 显式标准优先与回落无标准
- **GIVEN** 调用方显式提供了非空成功标准，或 planner 调用失败回落为单子任务
- **WHEN** 拆解完成
- **THEN** 显式标准 SHALL 覆盖生成标准；回落的单子任务计划不带生成标准

#### Scenario: 进度追踪
- **GIVEN** 任务执行中
- **WHEN** 子任务开始、失败、重试
- **THEN** ProgressTracker 的 started / completed / failed 计数随之更新并反映整体目标推进

#### Scenario: 任务级判定
- **GIVEN** 全部子任务通过验收且计划带有成功标准
- **WHEN** 任务进入 VERIFYING
- **THEN** 判定器接收 Goal、成功标准与子任务结果，判定通过才判 `DONE`

#### Scenario: 未达标重试/重规划
- **GIVEN** 子任务进度未达标或任务级判定未通过
- **WHEN** 进度监控检测到偏差
- **THEN** 触发重新拆解（预算未用尽）或判 `FAILED`，衔接状态机 RECOVERING

#### Scenario: 任务级未达标携带原因与标准重拆
- **GIVEN** 任务级判定器返回未通过并给出具体原因
- **WHEN** 恢复回路触发重新拆解
- **THEN** 重拆请求包含该原因与全部任务级成功标准（各自有界），不再只有原目标与已完成列表

#### Scenario: 判定器异常 fail-closed
- **GIVEN** 任务级判定器抛出异常或返回非法结果
- **WHEN** 任务进入 VERIFYING
- **THEN** 判定按未达标处理并进入恢复回路，任务不裸崩、不静默判 `DONE`
