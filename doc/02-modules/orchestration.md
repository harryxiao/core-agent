# 模块设计：任务规划与编排（Task Planning & Orchestration）

> 对应规格：`doc/openspec/specs/orchestration/spec.md` ｜ 接口：`doc/03-interfaces/orchestration-interface.md`
> 定位：**L3 之上**，把零散的 LLM 循环升级为可处理长周期复杂任务的执行引擎。

---

## 1. 模块定位

单一 loop 只能处理"一轮一步"的短任务；复杂目标需要**跨多轮、多子任务、甚至多智能体**的编排。

本模块在 AgentLoop（L3）之上提供三层基础能力：**状态机管理、子任务拆解、多 Agent 协同**，并新增**并行扇出、目标监控、优先级调度**三项运行时能力，使 CORE 从"循环"升级为"执行引擎"。

---

## 2. 内部组成

```
Orchestrator（L3.5）
├── StateMachine      任务状态机：状态转移规则，防跑偏/死循环
├── SubtaskDecomposer 子任务拆解器：大目标 → 分步 Todo，逐步校验
├── MultiAgentRouter  多 Agent 协同：能力匹配 + 消息协议交接
└── ProgressTracker   进度与校验：每步完成校验后再推进
```

---

## 3. 关键设计

### 3.1 状态机管理

```
CREATED → PLANNING → EXECUTING → VERIFYING → DONE
                     ↑            │
                     └── RECOVERING（异常恢复）
                          ↑       │
                          └── FAILED（熔断后终止）
```

- 定义合法状态转移规则（转移表），非法转移被拒绝。
- 每步执行后检查"是否仍在向目标推进"（进度哨兵），检测到跑偏/死循环 → 触发 RECOVERING 或 FAILED。

### 3.2 子任务拆解器

- 把大目标拆为可校验的分步 Todo 列表（每项含：目标、验收标准、依赖关系）。
- 执行采用 **DAG 拓扑序**：依赖完成才启动下一步；无依赖项可并行。
- **逐步校验**：每完成一个子任务，用其验收标准校验结果，通过才推进；失败则回退重试或重新规划。子任务**执行单元**返回失败态（循环未达成 / 异常终止 / 预算耗尽）时亦 **fail-closed**（不因合成回复非空而假成功，change 0126）。

### 3.3 多 Agent 协同编排

- 注册多个不同能力的子 Agent（各自是一组插件 + profile）。
- MultiAgentRouter 按任务类型匹配最合适的 Agent。
- 通过**标准化消息协议**完成交接：`TaskHandoff {task, context_pack, acceptance, deadline}`。
- 交接上下文由 context 模块打包（信息地图 + 必要事实），避免全量塞入。

### 3.4 并行扇出（fan-out / fan-in 波次调度）

- 子任务 DAG 按依赖拓扑分层为**波次（wave）**：同一波次内子任务无相互依赖，可并行 fan-out 到多个执行单元。
- 波次内全部子任务完成并经 **fan-in 汇总校验**通过后，才推进下一波次；校验失败触发状态机 RECOVERING。
- 并行度受**资源上限**约束：超出上限时同波次分批执行。
- **同波次调度策略**（change `0123`／ADR-0116）：`TaskScheduler._fan_out` 的 `Semaphore` 上限由
  `_wave_limit(本波次)` 给出 —— 策略 `off`（缺省）取 `max_concurrency`（与引入前**逐字一致**）；
  策略 `difficulty` 时，本波次**存在** `difficulty = "hard"` 的子任务则上限取 `1`（整波串行，按优先级
  降序逐个），否则仍取 `max_concurrency`。**粒度是波次而非子任务**；策略**只收窄不放大**并发，
  且**不改**波次划分（依赖拓扑仍是**硬约束**）。两值经 `configuration` 校验期拦截非法取值
  （`INVALID_DISPATCH_POLICY` 为构造期 fail-fast），并由**组合根**注入（缺省 `4` 与既有行为同值 ⇒
  不接线不暴露，故**必须**显式传）。
- **检查点会话归因**（change `0190`／ADR-0180）：波次收拢 / 终态检查点回调（`CheckpointFn` /
  `DoneFn`，第 4 参 `session_id`）携带**发起方会话标识**（空串 = 未归属照实记录，**不**写占位值）
  ⇒ 检查点的会话归属元数据与实际发起会话一致；CLI `task` 新任务经共享注册表铸会话（mode `cli`）、
  `--resume` 续跑复用检查点既有会话（同一任务跨续跑不分裂）。
- **完成回调卸载**（change `0196`／ADR-0186）：任务**完成回调**（`on_done`）经 `asyncio.to_thread`
  **卸载至工作线程**执行，**不**在事件循环上同步阻塞（守「异步执行单元契约」的「收尾回路不阻塞」）——
  回调可承载模型调用等重活而不阻塞流式产出；调用时机（`DONE` 达成后**一次**）、顺序（`task_finished`
  之前、检查点之后）与终态判定 **逐字不变**。波次检查点 `_checkpoint` **不**卸载（判据是「是否承载
  模型调用」而非「是否同步」）。

### 3.5 目标监控（Goal / SuccessCriteria + ProgressTracker）

- 任务拆解时定义 **Goal 与 SuccessCriteria（SMART：具体/可度量/可达成/相关/有时限）**，子任务验收标准对齐父目标。
- **ProgressTracker** 独立负责进度追踪：记录每子任务进度，汇总为整体目标推进度。
- 进度未达标时触发重试或重新规划（衔接状态机 RECOVERING）。

### 3.6 优先级调度（priority）

- 子任务带 **priority** 优先级字段；就绪队列（同波次无依赖子任务）按优先级降序调度。
- 同优先级按入队序（FIFO）稳定执行；priority 缺省时取默认值。
- 优先级仅在同波次就绪子任务间生效，跨波次仍遵守 DAG 拓扑序。

---

## 4. 与 loop 的关系

- Orchestrator **不替换** loop，而是驱动多个 loop 实例 / 复用单 loop 处理子任务。
- 每个子任务仍遵守 loop 的四阶段 + 确认门 + 可逆效应约束。
- 状态机事件通过 L0 EventBus 发布，observability 模块订阅做遥测。
- **子任务经 `astream` 流式驱动**（change 0121 / ADR-0114）：编排层消费子 Agent 的事件流，
  把里程碑事件（`action_started` / `action_completed` / `step_completed`）按**封闭白名单**
  转译为 `subtask_progress` 实时外发（附加通道，不改终态判定）；终态归一复用
  `core.loop.collect_result`（与 `DefaultLoop.arun` 同一实现，避免语义漂移）。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 非法状态转移 | 拒绝并记录，不破坏任务状态 |
| 子任务校验失败 | 回退重试（有限次）→ 重新规划 → 标记 FAILED |
| 检测到死循环 | 触发 RECOVERING，注入"换策略"提示或人工介入 |
| 交接目标 Agent 不可用 | 降级到备用 Agent 或转为人工审批 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/orchestration-interface.md`
- 规格：`doc/openspec/specs/orchestration/spec.md`
- 测试：`doc/04-testing/test-cases.md`（ORCH 系列）
