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
├── ProgressTracker   进度与校验：每步完成校验后再推进
├── BackgroundAgentRegistry 后台子 Agent：非阻塞派发 + 按会话完成通知 + 跨重启登记与跨进程归属（change 0270/0279/0283）
├── task_retry_tool   后台任务重入队：interrupted/failed/cancelled → 新任务（change 0279）
└── AutoResumeState 自动续跑退避账本：跨进程有界尝试（change 0278）
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
- **有限恢复回路**（change `0246`／ADR-0234）：失败项**只重跑 1 次**
  （`_MAX_SUBTASK_RETRIES=1`，已完成子任务不重跑，重试目标带上次失败原因）；仍失败 ⇒
  **重新拆解 1 次**（`_MAX_REPLANS=1`，输入为原目标 + 已完成摘要 + 失败原因）。预算耗尽 ⇒
  `FAILED`（沿用最后错误码，载荷带 `attempts`/`replans`）。重拆清空该任务旧完成集/结果
  （新 DAG 可能复用 id），`Plan.replans` 随检查点持久化。子 Agent 执行异常归一为子任务失败
  （结构化错误保留原码，其余 → `SUBTASK_EXECUTION_FAILED`，取消透传）；空计划直接 `FAILED`。
- **运行中取消与断流**（change `0249`／ADR-0238）：`cancel` 置 per-task 协作信号并**立即取消
  在途波次**，执行流在拆解后 / 波次前后 / 任务级判定后观察信号并以 `TASK_CANCELLED` 终止
  （终态重复取消幂等）；`astream` 的 `finally` 覆盖任意退出路径 —— 取消在途扇出、清
  `_results` / 取消登记 / 波次登记，消费方断流（未达终态）按 `FAILED` 收口并 trace
  `task_aborted`。取消**不回滚**已执行子任务的副作用与检查点结果。

### 3.3 多 Agent 协同编排

- 注册多个不同能力的子 Agent（各自是一组插件 + profile）。
- MultiAgentRouter 按任务类型匹配最合适的 Agent。
- 通过**标准化消息协议**完成交接：`TaskHandoff {task, context_pack, acceptance, deadline, priority, session_id}`；
  **全部字段被消费**（change `0247`／ADR-0235）——`context_pack`（原目标 + 依赖结果）与
  `acceptance` 进入 prompt，`priority` 决定就绪队列次序，`deadline` 经 `asyncio.timeout` 包住执行
  （超时归一 `SUBTASK_TIMEOUT`），`session_id` 透传子 loop。
- 交接上下文由 `handoff.build_context_pack` 打包并**有界**（总预算 `DEFAULT_CONTEXT_TOKENS`，
  单字段 `MAX_HANDOFF_CHARS`），避免全量塞入。
- **统一执行器**：beast / pet / 主任务复用 `orchestration/handoff.py`（`build_context_pack` /
  `render_handoff` / `stream_handoff` / `run_handoff`），上下文隔离仍由各自 `session_id` 保证；
  beast/pet 传空上下文 ⇒ `render_handoff` 逐字返回任务文本（行为不变）。
- **委托会话透传**：主循环在 `_act` 期间把当前 `session_id` 写入 `current_session_id` ContextVar，
  `runtime._dispatch` 读取后转交子 Agent ⇒ 委托轨迹归入发起会话；`source` 命名空间划分不变
  （`exclude_source_prefixes=("beast.","pet")`）。

### 3.4 并行扇出（fan-out / fan-in 波次调度）

- 子任务 DAG 按依赖拓扑分层为**波次（wave）**：同一波次内子任务无相互依赖，可并行 fan-out 到多个执行单元。
- 波次内全部子任务完成并经 **fan-in 汇总校验**通过后，才推进下一波次；校验失败 ⇒ 失败项
  重试 1 次，仍失败 ⇒ 状态机 `RECOVERING` 并重新拆解 1 次，预算耗尽 ⇒ `FAILED`（change `0246`／ADR-0234）。
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
  **标准默认由 planner 随拆解生成**（顶层 `success_criteria`，2-5 条可客观判定真伪、覆盖整体目标
  而不复述子任务 acceptance；`DecomposeResult`）；调用方显式非空标准优先；planner 失败回落的单子任务
  计划**不带**标准（change `0248`／ADR-0236）。重新拆解时原标准非空则保留。
- **任务级判定**：`LLMTaskVerifier` 对照 Goal + 标准 + 子任务结果判任务是否达成（输入脱敏、有界、
  单次重试；异常/非法返回 fail-closed）。组合根缺省注入（开启）；带标准未注入判定器 ⇒
  `MISSING_SUCCESS_CHECKER` fail-fast。
- **ProgressTracker** 独立负责进度追踪：维护 `started` / `completed` / `failed` 三态，`progress(task_id)`
  返回三计数；重试开始与完成清除 `failed`，重新拆解清空三态。
- 进度或任务级判定未达标时触发重试或重新规划（衔接状态机 RECOVERING，重拆预算耗尽转 `FAILED`）。

### 3.6 优先级调度（priority）

- 子任务带 **priority** 优先级字段；就绪队列（同波次无依赖子任务）按优先级降序调度。
- 同优先级按入队序（FIFO）稳定执行；priority 缺省时取默认值。
- 优先级仅在同波次就绪子任务间生效，跨波次仍遵守 DAG 拓扑序。

### 3.7 后台委托与完成通知（change `0270`／ADR-0260）

- **注册表归编排层**：`core/orchestration/background.py::BackgroundAgentRegistry` 管理的是
  **子 Agent 的 loop**（`spawn` → `asyncio.Task`），与 L1 `ProcessRegistry`（OS 进程）语义分离。
  `spawn` 立即返回 `task_id`；任务强引用保存在注册表直至终态。
- **状态机**：`running → done | failed | cancelled`（不可逆）。子 Agent 抛错 ⇒ `failed`，`error`
  只记**异常类型名**；`LoopResult.failed=True` ⇒ `failed`；取消同步落 `cancelled`。每个终态都
  产生一条通知。
- **完成通知**：按**会话**入界（每会话 32 条，丢最旧），`drain_notices` / `render_notices` 为
  **一次性取走**；主 loop 经 `notices_consult` 在轮首取用，planner 出「后台任务通知：」独立块。
  `tools.tasks` 只读清单，**不**清空通知。
- **有界**：运行中任务 8（超限 `BACKGROUND_TASKS_FULL`，不排队）；单轮渲染 10 条；单行 400 字符；
  单任务保留回复 4000 字符。
- **注入面**：`tools.delegate` 的 `background` 缺省 `false`（阻塞语义逐字不变）；`tools.tasks`
  与通知钩子**只挂主工具面 / 主 loop**，子 Agent 结构上不可见（不可再委托、不可窥视清单）。
- **权限**：`tools.tasks` 由 `PolicyEngine` 按**字面量工具 id** 判 `read`；`tasks` 词元/前缀
  不放宽（deny-by-default 纪律）。

### 3.8 未完成任务自动续跑（change `0278`／ADR-0268）

- **显式 opt-in**：`orchestration.auto_resume` 缺省 `false`；关闭时启动面仍「纯扫描 + 呈现」。
  开启后仅 `core-agent task` 入口在起新任务前消费 `Runtime.pending_resumes()`，逐条
  `asyncio.run(astream)` 串行续跑（与人工 `--resume` 同一流式管线）；`serve` / TUI / `mcp serve`
  仍只呈现（不跨事件循环共享调度器）。
- **重建口径与 `--resume` 同源**：每任务取**时间戳最新**的可读快照，重建 `TaskResume`
  （plan / 已完成子任务 / 交接回复 / 发起会话）；跳过 `done=true`、`turn.` 前缀与 `kind=turn`、
  无计划或快照全损坏者（只告警 task id，不中断其余任务）。
- **跨进程有界**：`AutoResumeState` 把 `task_id → {attempts, last_ts}` 原子写入
  `$CORE_STATE_DIR/auto-resume.json`（`0600`，仅计数与时间戳，不含正文/密钥）。首次即到期；
  第 n 次尝试后等 `min(60·2^(n-1), 3600)` 秒；**最多 3 次**自动尝试。尝试**执行前**记账
  （崩溃也消耗次数），成功清零，失败保留检查点等待下次退避重试。
- **显式入口不受限**：`core-agent task --resume-all` 续跑全部未完成任务，忽略配置开关、退避与
  次数上限（运营商显式重试），仍记录尝试并在成功时清零。
- **默认关闭测试锚**：关闭时不读取/不执行 `pending_resumes()`，启动呈现逐字不变。

### 3.9 后台任务跨重启登记与重入队（change `0279`／`0283`／ADR-0269／0273）

- **落盘**：注册表接受 `state_path`（runtime 注入 `$CORE_STATE_DIR/background-tasks.json`；
  缺省 `None` ⇒ 纯内存，既有构造零变化）。写盘为锁内「读-合并-写」：取同目录
  `.{name}.lock` 的短独占建议锁（POSIX `flock` / Windows `msvcrt.locking`，取锁失败降级为
  无锁写），锁内重读磁盘、只用本实例**变更过的条目**覆盖，其余条目保留磁盘版本 —— 并发
  进程不会互相覆盖登记或回滚对方的更新。随后同目录临时文件 + `fsync` + `os.replace`，
  `0600`；最多保留最新 **64** 条；写失败告警一次、不阻断任务。
- **字段**：`task_id / agent_id / task / status / started_at / finished_at / session_id / error /
  owner_pid / owner_start`。`task`/`error` **写读两侧**经 `redact_secrets` 并有界（120 / 200
  字符）；**不落 `reply`**；`session_id` 与归属字段只在文件中（`info()` 对模型不可见）。
- **跨进程归属**：加载时 `running` 按 owner 判定 —— owner 存活（pid 存在且启动标识一致）⇒
  **保持 `running`**，本进程只观察、不取消/不接管、不重放通知（`task_retry` 按 running 拒绝）；
  owner 已退出、owner 信息缺失（旧格式）或 pid 存活但启动标识不符（pid 复用）⇒
  `running → interrupted`（`finished_at=None`，`error="进程重启导致中断"`）。
  `interrupted` 是终态：不占运行名额、不可取消、不重放完成通知；`tools.tasks` 可查。
- **重入队**：`tools.task_retry(task_id)` 只接受 `interrupted / failed / cancelled`；按登记正文
  重新 `MultiAgentRouter.match` 后 `spawn` 新任务（恢复原会话，原 `task_id` 终态不变）；
  `running` / `done` 结构化拒绝；容量上限返回 `BACKGROUND_TASKS_FULL`。
- **权限**：词元 `{task, retry}` 无只读/写词元 ⇒ `HIGH_RISK`（审批门）；coeffect
  `task:write` 显式注册、`reversible=False`；只挂主工具面。
- **一致性**：文件损坏 ⇒ 告警一次并按空登记处理，不阻断启动/主循环。

### 3.10 无人值守 profile（change `0280`／`0281`／ADR-0270／0271）

- **组合而非新模式**：无人值守 = `permission.mode=auto-approve` + 可选
  `permission.auto_approve_coeffects` + 可选 `orchestration.task_timeout` /
  `task_token_budget` + 可选 `orchestration.failure_notify_file` /
  `failure_notify_webhook`。五项缺省 `"" / 0 / 0 / "" / ""` ⇒ 全部关闭，既有路径逐字不变。
- **整任务墙钟在入口**：`entry._run_task_stream` 以 `asyncio.wait_for` 包住完整
  `_stream_task`，覆盖 fresh / `--resume` / 自动续跑 / `--resume-all`；超时 `TASK_TIMEOUT`、
  退出码 1、**保留最近波次检查点**。`serve` / TUI / 编程式调用不受该配置约束。
- **token 预算在调度器**：`LoopResult.token_used`（上下文估算，缺省 0）由子任务回流；调度器按
  `task_id` 累计，越过正预算 ⇒ `TASK_TOKEN_BUDGET_EXCEEDED`，**禁重试、禁重拆**，终态
  `FAILED`（`extra={"token_used","token_budget"}`），`_release` 清累计。预算 0 = 关闭，
  负数构造期拒绝。
- **失败通知（本地）**：`entry._notify_failure` 向 JSONL 追加一行（`ts/event/task_id/
  session_id/code/reason/goal`），`reason`/`goal` 经 `redact_secrets` + 500 字符截断，新建
  文件 `0600`；写失败只 stderr 告警、不改变任务结局。`TASK_CANCELLED` 不通知；超时与自动
  续跑失败显式通知。
- **失败通知（远程，change 0281）**：`failure_notify_webhook` 非空时，同一失败收口另向该
  URL 单次 `POST` 通用 JSON（`text` + 上述字段）。`core/orchestration/notify.py` 仅用 stdlib
  `urllib.request`，超时 5s、不重试、不排队。两个 sink **相互独立**（任一失败不阻止另一个，
  只 stderr 告警）。非空 URL 只接受 `http(s)` + 非空 host；**URL 可能内嵌令牌 ⇒ 校验错误与
  推送失败告警均不回显 URL**。

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
| 子任务校验失败 | 仅失败项重试 1 次 → 重新拆解 1 次 → 预算耗尽标记 FAILED |
| 子 Agent 执行抛异常 | 归一为子任务失败（保留结构化错误码），进入同一恢复回路 |
| 计划为空 | 直接 FAILED（不因空标准视为通过而判 DONE） |
| 检测到死循环 | 触发重拆（注入"换策略"提示）；预算耗尽转 FAILED |
| 交接目标 Agent 不可用 | 降级到备用 Agent 或转为人工审批 |
| 后台任务已达运行上限 | `BACKGROUND_TASKS_FULL` 结构化拒绝（不排队；change 0270） |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/orchestration-interface.md`
- 规格：`doc/openspec/specs/orchestration/spec.md`
- 测试：`doc/04-testing/test-cases.md`（ORCH 系列）
