# Delta — change 0246（orchestration R2 / R4）

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

### Requirement: 断点续跑
系统 SHALL 支持长任务挂起、恢复与取消（断点续跑）：挂起时持久化执行上下文与中间结果，恢复时从断点继续而非重头执行，取消时释放已占用资源。检查点持久化 SHALL 携带**发起方会话标识**（发起会话的 `session_id`，空串 = 未归属照实记录）；SHALL NOT 写占位值（如 `"default"`）——检查点的会话归属元数据 SHALL 与实际发起会话一致（发起方未携带会话时为空串）。波次检查点与终态检查点 SHALL 同口径。

检查点 SHALL 持久化**重新拆解计数**（`Plan.replans`）；续跑重建 SHALL 保留该计数，SHALL NOT
重置为 0。子任务重试次数为**进程内**有界计数，不跨进程持久化。

#### Scenario: 任务挂起
- **GIVEN** 一个长时间运行的任务
- **WHEN** 触发挂起操作
- **THEN** 执行上下文与中间结果被持久化，任务进入 SUSPENDED 状态，已完成的子任务结果不丢失

#### Scenario: 任务恢复
- **GIVEN** 任务处于 SUSPENDED 状态且断点上下文已持久化
- **WHEN** 触发恢复操作
- **THEN** 从断点继续执行，已完成的子任务不重复执行（幂等恢复）

#### Scenario: 任务取消
- **GIVEN** 任务处于运行或挂起状态
- **WHEN** 触发取消操作
- **THEN** 任务终止并释放已占用的执行单元与资源，已持久化的断点上下文按策略清理

#### Scenario: 检查点携带发起会话标识
- **GIVEN** 一次携带会话标识（非空）的任务执行
- **WHEN** 波次收拢或任务终态触发检查点持久化
- **THEN** 检查点的会话归属元数据等于该发起会话标识（非占位值）；未携带会话时为空串（照实记录未归属）

#### Scenario: 续跑保留重新拆解计数
- **GIVEN** 一次任务已用掉重新拆解预算（`Plan.replans=1`）并写入检查点
- **WHEN** 进程退出后从该检查点续跑
- **THEN** 重建的 `Plan.replans` 仍为 1，恢复回路不会再次获得重新拆解预算
