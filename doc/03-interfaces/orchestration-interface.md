# 接口设计：任务编排（Orchestration Interface）

> 模块：`02-modules/orchestration.md` ｜ 规格：`openspec/specs/orchestration/spec.md`

---

## 1. 状态机接口

```python
class TaskState(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    SUSPENDED = "suspended"
    RECOVERING = "recovering"
    FAILED = "failed"
    DONE = "done"

class StateMachine:
    def transition(self, task_id: str, to: TaskState) -> None:
        """执行合法状态转移；非法转移抛 InvalidTransition。"""

    def state(self, task_id: str) -> TaskState: ...
```

合法转移表：

```
CREATED→PLANNING→EXECUTING→VERIFYING→{EXECUTING(重试)|DONE|RECOVERING}
EXECUTING→SUSPENDED（挂起）；SUSPENDED→EXECUTING（恢复）
RECOVERING→EXECUTING | FAILED
任意态→FAILED（熔断/人工终止）
```

---

## 2. 子任务拆解接口

```python
class SubtaskDecomposer:
    def __init__(
        self,
        planner: Planner | None = None,        # Callable[[str], list[Subtask] | DecomposeResult | Awaitable[...]]
        verifier: Verifier | None = None,      # Callable[[Subtask, Any], VerifyResult | Awaitable[...]]
    ) -> None: ...

    async def decompose(self, goal: str, success_criteria: list[str] | None = None) -> Plan:
        """大目标 → 分步 Todo（含验收标准与依赖 DAG）。

        成功标准优先级：显式非空 > planner 随拆解生成 > 空（change 0248）。
        注入 planner 时经其生成子任务（支持异步）；未注入默认单子任务（离线）。
        """

    async def verify(self, subtask: Subtask, result: Any) -> VerifyResult:
        """验收门：通过才推进。有 acceptance 且注入 verifier 时经其判定（LLM 对照）；
        无 acceptance 退化为离线非空判定（不调用模型）。"""

@dataclass
class Subtask:
    id: str
    goal: str
    acceptance: str             # 验收标准（Given/When/Then 或断言）
    depends_on: list[str]       # 依赖子任务 id（DAG 拓扑序）
    priority: int = 0           # 优先级：就绪队列内降序调度，缺省取默认值
    difficulty: str = "medium"  # 难易度：easy / medium / hard（缺省 medium；change 0123）

@dataclass
class Plan:
    subtasks: list[Subtask]
    order: list[str]            # 拓扑排序后的执行顺序
    goal: str                   # 顶层目标
    success_criteria: list[str] # SMART 成功标准（可度量）
    waves: list[list[str]]      # 波次划分：每波为无依赖子任务 id 列表

@dataclass
class VerifyResult:
    passed: bool
    reason: str

@dataclass
class DecomposeResult:
    """拆解产物：子任务集 + 任务级成功标准（planner 生成；change 0248）。

    返回 list[Subtask] 的既有 planner 桩继续兼容（视为无生成标准）。
    """
    subtasks: list[Subtask]
    success_criteria: list[str] = field(default_factory=list)
```

### 2.1 LLM 拆解 / 验收适配器

```python
class LLMSubtaskPlanner:
    """经 llm-provider acompletion 产子任务 DAG；失败/不可解析回落单子任务。"""
    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None: ...
    async def __call__(self, goal: str) -> DecomposeResult: ...

class LLMVerifier:
    """经 acompletion 对照 acceptance 判定结果；调用失败/不可解析 fail-closed。"""
    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None: ...
    async def __call__(self, subtask: Subtask, result: Any) -> VerifyResult: ...

class LLMTaskVerifier:
    """任务级判定器：对照整体目标 + 成功标准 + 子任务结果判任务是否达成（change 0248）。

    复用验收判定 prompt 与 fail-closed 路径；输入脱敏、有界（4000 字符），单次重试。
    criteria 为空时直接判过、不调用模型。
    """
    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None: ...
    async def __call__(
        self, goal: str, criteria: list[str], outcomes: list[SubtaskOutcome],
    ) -> VerifyResult: ...
```

- 拆解 prompt 约束输出 `{"success_criteria": [...], "subtasks": [{"id","goal","acceptance",
  "depends_on","priority","difficulty"}]}`；`success_criteria` 为 2-5 条可客观判定真伪的标准
  （覆盖整体目标、不复述子任务 acceptance）。逐项校验（id/goal 非空、depends_on 引用已声明 id），
  非法项剔除；标准只收非空字符串、strip、保序去重、至多 5 条；全非法则回落单子任务（回落
  **不带**标准 —— 同源判定 fail-closed 不得把任务拖死）。
- `difficulty` 是**模型自报的弱信号**：归一为三档（去空白 + 小写），集合外取值回落 `medium`
  —— **不剔除**子任务、不抛裸异常（与 `priority` 非整数取 0 同口径；与**配置键**非法即阻断启动的
  口径**有意不同**，见 §4）。
- 验收 prompt 输出 `{"passed": bool, "reason": str}`；解析失败按不通过处理（fail-closed）。

### 2.2 编排执行与进度事件

```python
class TaskScheduler:
    def __init__(self, ..., max_concurrency: int = 4, difficulty_policy: str = "off",
                 tracer: Tracer | None = None,
                 success_checker: SuccessChecker | None = None,
                 task_token_budget: int = 0) -> None:
        """``task_token_budget``：整任务 token 预算（change 0280 / ADR-0270）。
        按 ``LoopResult.token_used``（上下文估算）逐子任务累计；越过正预算 ⇒ 当前子任务
        ``TASK_TOKEN_BUDGET_EXCEEDED``，**禁重试、禁重拆**，终态 ``FAILED``
        （``extra={"token_used","token_budget"}``）。``0`` = 关闭（既有行为逐字不变）；
        负数构造期 ``OrchestrationError(INVALID_DISPATCH_POLICY)``。生产值由组合根注入
        ``orchestration.task_token_budget``。"""

    async def run(
        self, task_id: str, goal: str, success_criteria: list[str] | None = None,
        *, plan: Plan | None = None, completed: set[str] | None = None,
        results: dict[str, str] | None = None, session_id: str = "",
    ) -> list[SubtaskOutcome]:
        """同步语义收口：消费 astream，终态失败按原错误码抛 OrchestrationError。
        plan/completed/results 为断点续跑注入面（跳过拆解与已完成子任务、
        重建依赖结果上下文）。``session_id`` 为**发起方会话标识**（缺省空串 = 未归属），
        透传至子 Agent 执行 ⇒ 子任务轨迹按发起会话归属（change 0114 / ADR-0107）。"""

    def astream(self, task_id, goal, success_criteria=None, *, plan=None, completed=None,
        results=None, session_id=""
    ) -> AsyncIterator[LoopEvent]:
        """流式任务执行（进度事件）：task_started / plan_ready / wave_started /
        subtask_started / subtask_progress / subtask_completed / task_checkpoint /
        task_retrying / task_replanning / task_finished / task_failed；
        关键节点（拆解/验收/检查点/终态）经 tracer 写 trace。"""

    def cancel(self, task_id: str) -> None:
        """取消运行中任务：置协作取消信号、立即打断在途波次、转 FAILED 并释放
        进度/结果上下文；终态任务重复取消幂等（change 0249 / ADR-0238）。"""
```

- **任务级判定**（change 0248）：`SuccessChecker = Callable[[str, list[str], list[SubtaskOutcome]],
  VerifyResult | Awaitable[VerifyResult]]`（Goal / 成功标准 / 子任务结果）。计划带标准时于
  `VERIFYING` 调用判定器，未达标以 `PROGRESS_NOT_MET` 进入恢复回路（重拆预算未用尽则重拆，
  否则 `FAILED`）；判定器异常或返回非法值归一 **fail-closed**（判未达标），不裸崩、不静默放行；
  带标准但未注入判定器 ⇒ `MISSING_SUCCESS_CHECKER`（fail-fast）。`ProgressTracker` 维护
  `started` / `completed` / `failed` 三态，`progress(task_id)` 返回三计数字典；重试开始与完成
  清除 `failed`，重新拆解清空三态。
- CLI 入口：`core-agent task <目标> [--task-id ID | --resume ID]` 流式打印进度事件；
  `--resume` 从该 task-id 最新检查点重建 Plan 与已完成集，续跑未完成子任务；
  检查点经 CheckpointStore 落盘 `$CORE_STATE_DIR/checkpoints.jsonl`（缺省
  `~/.core/state/`），跨进程 kill/重启可续跑。
- **无人值守护栏**（change 0280 / 0281 / ADR-0270 / 0271）：`task` 入口按
  `orchestration.task_timeout` 用 `asyncio.wait_for` 包住整条任务流（含 `--resume` /
  自动续跑 / `--resume-all`）；超时打印 `[task_timeout]`、退出码 1、保留最近波次检查点；
  失败（含超时与自动续跑失败）追加 JSONL 到 `orchestration.failure_notify_file`
  （脱敏、有界、`0600`；`TASK_CANCELLED` 不通知），并在
  `orchestration.failure_notify_webhook` 非空时向该 URL 单次 `POST` 通用 JSON
  （`text` + 同上字段；stdlib、5s、不重试）。两 sink 相互独立、失败只告警；三个配置缺省
  `0` / `""` / `""` ⇒ 不设限、不通知、不发请求。
- **文件型检查点**（change 0230 / ADR-0237）：`FileCheckpoint(path=".core/scheduler-checkpoint.json")`
  满足 `CheckpointFn` 四参契约，JSON 落盘 `task_id / session_id / plan / completed / results`，
  同目录 `.tmp` + `os.replace` **原子写**；`load(task_id=None)` 读回（损坏/缺失返回 `None`，
  传入任务 id 不匹配亦返回 `None`）。**opt-in**：未显式传入时调度器不自行落盘，上层注入的回调
  仍优先、不产生文件 I/O。
- **检查点会话归因**（change 0190 / ADR-0180）：检查点回调 `CheckpointFn` / `DoneFn` 签名为
  `(task_id, outcomes, plan, session_id)` —— 第 4 参即发起方会话标识（空串 = 未归属照实记录，
  **不**写占位值如 `"default"`）；波次检查点与终态检查点同口径。CLI `task` 新任务经共享会话
  注册表铸会话（mode `cli`，与其他一次性入口同一注册表）并透传至 `astream`；`--resume` 复用
  检查点携带的既有会话（旧占位值视作未归属并提示，不迁移旧数据）。
- **完成回调卸载**（change 0196 / ADR-0186）：任务完成回调（`on_done`）经 `asyncio.to_thread`
  **卸载至工作线程**执行 —— 回调 SHALL NOT 在事件循环上同步阻塞（可承载模型调用等重活）；调用
  时机（`DONE` 后**一次**）与检查点顺序**逐字不变**。波次检查点回调**不**卸载。
- **失败恢复**（change 0246 / ADR-0234）：波次失败 ⇒ 仅失败子任务**重试 1 次**
  （`subtask_started` / `subtask_completed` 载荷带 `attempt=2`，重试目标追加有界失败提示）；
  仍失败 ⇒ `VERIFYING→RECOVERING`，**重新拆解 1 次**（`task_replanning`，输入为原目标 +
  已完成摘要 + 失败原因）。预算耗尽 ⇒ `task_failed`，错误码沿用最后失败原因，载荷增
  `attempts` / `replans`。子 Agent 执行异常归一为失败（`OrchestrationError` 保留原码，
  其余 → `SUBTASK_EXECUTION_FAILED`，`CancelledError` 透传）。成功路径事件序列逐字不变。
- 依赖结果交接：子任务验收通过的回复（截断 2000 字符）注入 `depends_on` 后继
  子任务的执行输入（「前置子任务结果」段），并随 `SubtaskOutcome.reply` 写入
  检查点 outcomes，续跑时经 `results` 参数重建依赖上下文。
- **运行中取消与消费方断流**（change 0249 / ADR-0238）：`cancel(task_id)` 置 per-task 协作
  取消信号并**立即取消在途波次**（已登记 `_wave_tasks`），状态转 `FAILED`；执行流在拆解后 /
  每轮波次前 / 波次收拢后 / 任务级判定后观察信号，以 `task_failed {code: TASK_CANCELLED}`
  终止（状态不重复转移）。`astream` 以 `finally` 收口**任意退出路径**：取消在途扇出、清
  `_cancel_events` / `_wave_tasks` / `_results`；未达终态 ⇒ `FAILED` + trace `task_aborted`
  （`reason` 区分取消 / 断流，不伪装成功）；正常终态只释放缓存。终态任务重复取消**幂等**。
  **边界**：取消不能打断正在 `await` 的拆解 / 任务级判定（返回后才观察）；已执行子任务的
  副作用与检查点结果不回滚；消费方只 `break` 而不 `aclose()` 时生成器延迟终结，调用方应显式
  `aclose()`。`CancelledError` 仅在协作取消（信号已置）时被安静收拢，外部取消照常透传。
- **恢复计数持久化**（change 0246 / ADR-0234）：`Plan.replans` 随检查点往返（旧检查点缺键
  ⇒ 0）；重拆前先落计数与检查点，续跑不重置恢复预算。重拆会清空该任务的已完成集与结果
  上下文（新 DAG 可能复用 id）。子任务重试次数为进程内计数，不跨进程持久化。
- 事件复用 `core.loop.LoopEvent`（type + dict 载荷），与 loop/ui 事件面同构；
  载荷携带 UI 折叠详情所需字段：`subtask_started` 含 `goal` + `acceptance`（验收
  标准）+ `attempt`，`subtask_completed` 含 `reason`（判定）+ `reply` 节选（600 字符）；
  `plan_ready` 含 `replan`（当前计划已用的重拆次数）。
- **子任务运行态回流**（change 0121 / ADR-0114）：子 Agent 经 `astream` 流式执行，
  里程碑事件实时转译为 `subtask_progress`（**附加通道**，与 `subtask_started` /
  `subtask_completed` 同源同序，**不**新建旁路；终态判定仍由 `SubtaskOutcome` 决定）。
  载荷形状 `{"task_id", "subtask_id", "event", "data", "ts"}`：`event` 为内层事件类型，
  `data` 为**按类型白名单**取键的载荷子集。白名单（`_PROGRESS_FIELDS`）：

  | 内层 `event` | `data` 允许键 |
  |---|---|
  | `action_started` | `round` / `tool_id` / `args` |
  | `action_completed` | `round` / `tool_id` / `ok` / `duration_ms` / `output` |
  | `step_completed` | `round` / `failed` |

  **表外事件类型（含未来新增）一律不外发**；模型流式原文 `reply_delta` **有意排除**
  （洪泛 + 暴露未定稿原文）。终态归一由 `core.loop.collect_result`（`DefaultLoop.arun`
  的同一实现）承担，编排层与同步入口共用 ⇒ 语义单一真源。
- TUI 入口：REPL 会话内输入 `/task <目标>`，经 `UIAPILayer.run_task` 驱动同一编排器，
  进度事件以 `task.*` 前缀映射为 UI Event 流式呈现（与 CLI 同一格式化）。

### 2.3 同波次调度策略（change 0123 / ADR-0116）

```python
# 策略取值词表：off（缺省） / difficulty
DISPATCH_POLICIES: frozenset[str] = frozenset({"off", "difficulty"})

def _wave_limit(self, subtasks: list[Subtask]) -> int:
    """本波次并发上限：off ⇒ max_concurrency；difficulty 且**含 hard** ⇒ 1（串行）。"""
```

- **只收窄，不放大**：策略只影响 `_fan_out` 的 `Semaphore` 上限；`_build_waves` 的波次划分
  （依赖拓扑**硬约束**）**逐字不动** ⇒ 有依赖的子任务必分属不同波次，DAG 与断点续跑语义零回归。
- `off`（缺省）：同波次无依赖子任务并发扇出，上限 `max_concurrency` —— 与引入本策略前**逐字一致**。
- `difficulty`：同波次**存在** `difficulty == "hard"` 的子任务 ⇒ 该波次**整体**串行（按优先级降序
  逐个，峰值 1）；否则维持并发。**粒度是波次而非子任务**（部分并发部分串行无拓扑依据）。
- 构造器取值不在 `DISPATCH_POLICIES` ⇒ `OrchestrationError(INVALID_DISPATCH_POLICY)`（fail-fast）。
- **`max_concurrency` 必须由组合根注入**：构造缺省 `4` 与既有行为同值，不接线**不会暴露**
  （上限判据空转，与账本 E15 同型）⇒ `runtime.py` 装配时显式传配置值（`configuration-interface.md`）。
- 策略与上限均在 **`configuration` 校验期** 拦截非法取值（阻断启动，不静默退化）——与
  `difficulty` **归一**的口径**有意不同**（前者是人写的配置，后者是模型自报的弱信号）。

---

## 3. 多 Agent 协同接口

```python
@dataclass
class AgentProfile:
    agent_id: str               # 子 Agent 唯一 id
    capabilities: list[str]     # 能力标签（路由匹配依据）
    loop: LoopPlugin | None     # 可编排执行单元（arun/astream），handoff 时复用

@dataclass
class TaskHandoff:
    task: str
    context_pack: dict          # 由 context 模块打包的必要上下文
    acceptance: str
    deadline: float | None
    priority: int = 0           # 子任务优先级，就绪队列内降序调度
    session_id: str = ""        # 会话 ID：转交子 loop（arun(..., session_id=…)）⇒ 子 Agent 轨迹按自身会话归组

class MultiAgentRouter:
    def match(self, task: str) -> AgentProfile:
        """按能力标签打分匹配最佳子 Agent；无命中回落 fallback，均无则抛 NO_AGENT_MATCH。"""

    async def handoff(self, target: str, handoff: TaskHandoff) -> LoopResult:
        """显式交接任务给指定 Agent，异步执行并返回完整 LoopResult（见 loop-interface.md）；无匹配抛 NO_AGENT_MATCH。

        ``handoff.session_id`` 随调用转交子 loop（``arun(handoff.task, session_id=…)``）。
        """

    def handoff_stream(self, target: str, handoff: TaskHandoff) -> AsyncIterator[LoopEvent]:
        """流式交接（调度器入口）：保留 ``subtask_progress`` 事件回流；超时归一 SUBTASK_TIMEOUT。"""
```

**共享执行器（`orchestration/handoff.py`，change `0247` / ADR-0235）**：beast / pet / 主任务
（scheduler）复用同一套交接代码，上下文隔离仍由调用方各自的 `session_id` 保证：

```python
MAX_HANDOFF_CHARS = 2000       # 单字段（goal / result）字符上界
DEFAULT_CONTEXT_TOKENS = 2000  # context_pack 总预算（core.tokens.estimate_tokens 口径）

def build_context_pack(goal, dependencies, *, max_tokens) -> dict[str, Any]
    # {"goal": …, "dependencies": [{"id", "goal", "result"}]}；按依赖顺序装入，
    # 最后一条按剩余预算截断（CJK 感知），单条不超过 MAX_HANDOFF_CHARS。

def render_handoff(handoff: TaskHandoff) -> str
    # task + [原始目标] + [前置子任务结果] + [验收标准]；
    # context_pack 与 acceptance 均为空时**逐字返回 task**（beast / pet 行为不变）。

async def stream_handoff(loop, handoff, *, deadline=None) -> AsyncIterator[LoopEvent]
async def run_handoff(loop, handoff, *, deadline=None) -> LoopResult
    # deadline（秒；None 或 ≤0 = 不设限）经 asyncio.timeout 包住整段执行；
    # 超时取消子流并归一 OrchestrationError(SUBTASK_TIMEOUT)。
```

- **全字段消费**：调度器 `_build_handoff` 填充 `task` / `context_pack`（原目标 + 依赖结果）/
  `acceptance` / `deadline`（配置 `orchestration.subtask_timeout`）/ `priority` / `session_id`；
  `priority` 用于就绪队列排序，其余字段进入 prompt 或执行包装。
- **会话隔离**：执行器只转发 `session_id`，不解释其语义 —— 主任务 = 发起会话
  （`runtime._dispatch` 经 `current_session_id` ContextVar 透传给子 Agent）、beast = `beast.agent_id`、
  pet = 自身 UUID；`runtime.py` 的 `exclude_source_prefixes=("beast.","pet")` **不变**。
- **行为变更（有意）**：scheduler 路径的 prompt 新增「原始目标 / 前置结果 / 验收标准」段；
  beast / pet 传空上下文，`render_handoff` 逐字返回任务文本，prompt 与改造前一致。

### 3.1 后台委托注册表与任务清单（change `0270` / ADR-0260）

```python
@dataclass
class BackgroundTaskInfo:
    task_id: str
    agent_id: str
    task: str                       # 委托任务文本（对外快照截断 120 字符）
    status: str = "running"         # running / done / failed / cancelled / interrupted（终态不可逆）
    started_at: float = 0.0
    finished_at: float | None = None
    reply: str = ""                 # 子 Agent 回复（保留上界 4000 字符）
    error: str = ""                 # 失败原因（异常只留类型名 / 「子 Agent 报告失败」）
    owner_pid: int = 0              # change 0283：启动进程 pid（只入文件）
    owner_start: str = ""           # change 0283：进程启动标识（防 pid 复用；只入文件）

    def info(self) -> dict[str, Any]
        # 对模型暴露的只读快照：不含 session_id / owner_*；task / reply 有界截断

class BackgroundAgentRegistry:
    def __init__(self, state_path: Path | str | None = None, *,
                 max_running: int = 8, notice_cap: int = 32,
                 max_records: int = 64)
        # state_path 非空 ⇒ 元数据跨重启登记（0600 原子写、最多 max_records 条、
        # 损坏容忍）。加载时：owner 存活 ⇒ 保持 running（只观察不接管）；
        # 死 owner / 旧格式 / pid 复用 ⇒ running → interrupted。缺省 None ⇒ 纯内存。
        # 写盘为短独占锁内「读-合并-写」：只覆盖本实例变更过的条目。

    def spawn(self, loop: LoopPlugin, task: str, *,
              agent_id: str, session_id: str = "") -> str
        # 立即返回 task_id（asyncio.create_task）；超限抛
        # OrchestrationError(BACKGROUND_TASKS_FULL)，不排队
    def get(self, task_id: str) -> BackgroundTaskInfo | None
    def list(self) -> list[BackgroundTaskInfo]          # 全部任务，按发起序
    def drain_notices(self, session_id: str) -> list[BackgroundTaskInfo]  # 一次性取走
    def render_notices(self, session_id: str) -> str    # 取走并渲染（loop 轮首钩子）
    def cancel(self, task_id: str) -> bool              # 同步落 cancelled
    def cancel_all(self) -> None
    async def wait(self, task_id: str) -> BackgroundTaskInfo  # 取消/异常不抛
    def running_count(self) -> int

def render_notice_lines(tasks: list[BackgroundTaskInfo]) -> str
    # 最近 10 条、每任务一行、单行 ≤400 字符

def task_retry_tool(*, registry: BackgroundAgentRegistry,
                    match: Callable[[str], AgentProfile]) -> Tool
    # tools.task_retry：只接受 interrupted / failed / cancelled；按任务正文重新路由
    # 并 spawn 新任务（恢复原会话，原 task_id 终态不变）；running / done 拒绝；
    # coeffect task:write、reversible=False、只挂主工具面
```

**`tools.delegate` 参数面**：新增可选 `background: bool = false`。缺省/`false` ⇒ 既阻塞语义
（返回 `{ok, reply}`）逐字不变；`true` ⇒ 返回 `{ok: true, task_id, agent, status: "running"}`，
超限返回 `{ok: false, error}`。

**`tools.tasks`（只读）**：schema `{action: "list" | "status", task_id?: string}`；
`status` 未知 id 返回 `{task_id, found: false}`；coeffect `task:read`；只挂主工具面；
查询**不**清空待投递通知。重启后清单含 `interrupted` 任务（`reply` 为空）。

**`tools.task_retry`（重入队）**：schema `{task_id: string}`；成功返回
`{ok: true, task_id（新）, status: "running", agent, retried（原 id）}`；未知 id / running /
done / 容量上限均 `{ok: false, error}`。词元判 `HIGH_RISK`（审批门）；coeffect `task:write`；
只挂主工具面，子 Agent 不可见。

**登记文件**：`$CORE_STATE_DIR/background-tasks.json`，
`{version: 1, tasks: [{task_id, agent_id, task, status, started_at, finished_at,
session_id, error, owner_pid, owner_start}]}`；`task`/`error` 写读两侧经 `redact_secrets`
且有界；不落 `reply`；归属字段只入文件。并发写用同目录 `.{name}.lock` 短独占建议锁
（POSIX `flock` / Windows `msvcrt.locking`，`0600`；取锁失败降级为无锁写），锁内按
「磁盘视图 + 本实例 dirty 条目」合并后原子替换。

### 3.2 工作树租约与工具（change `0284` / ADR-0274）

```python
@dataclass(frozen=True)
class WorkspaceLease:
    worktree_id: str            # wt-<12hex>
    repo_root: str
    path: str
    branch: str                 # core-agent/wt-<12hex>
    agent_id: str
    created_at: float

    def as_metadata(self, changed: list[str] | None = None) -> dict[str, Any]
        # {id, path, branch, repo_root, changed_files}；不含任务正文 / session

class WorktreeManager:
    def __init__(self, root: Path | str, *,
                 backend_factory: Callable[..., GitBackend] = build_backend,
                 max_list: int = 50)
    def create(self, *, agent_id: str, start: Path | str | None = None) -> WorkspaceLease
        # 非 git / 无提交 / 状态根在仓库内 / 目录已存在 ⇒
        # OrchestrationError(WORKTREE_UNAVAILABLE)；sidecar 最后写，失败 best-effort 回滚
    def list(self) -> dict[str, Any]         # {"worktrees": [...], "truncated": bool}
    def discard(self, worktree_id: str, *, force: bool = False) -> dict[str, Any]
        # 不存在 ⇒ {"ok": True, "removed": False}（幂等）；
        # 篡改/越界登记 ⇒ {"ok": False}；脏树无 force ⇒ GIT_WORKTREE_DIRTY 语义
    def remove_quiet(self, lease: WorkspaceLease) -> None   # 创建后续失败时清理

def changed_files(lease: WorkspaceLease, *, cap: int = 20) -> list[str]
    # changed + untracked + conflicted 去重排序截断；GitError/OSError ⇒ []

def worktree_tools(*, manager: WorktreeManager,
                   is_running: Callable[[str], str | None]) -> tuple[Tool, Tool]
    # tools.worktree.list（worktree:read, READ）
    # tools.worktree.discard（worktree:write, HIGH_RISK, reversible=False）
```

**后台注册表扩展**：`spawn(..., workspace: WorkspaceLease | None = None)` 把租约传给 `_run`，
后者在 `use_workspace(lease.path)` 内 `arun`；终态后写入 `changed_files` 快照。
`BackgroundTaskInfo.worktree: dict`（缺省 `{}`）仅在非空时出现在 `info()`、通知（仅 id）与
登记文件（白名单字段：`id/path/branch/repo_root/changed_files`）。`task_retry_tool(...,
worktrees=manager)` 为新任务创建新工作树。`_PERSIST_VERSION` 保持 1，旧记录照常加载。

**布局**：`<root>/<repo_key>/<worktree_id>/` + `<worktree_id>.json`（`0600` 原子写）；
`repo_key = sha256(realpath(repo_root))[:12]`；根目录 `0700`。`root` 由组合根取
`$CORE_STATE_DIR/worktrees`。

---

## 4. 错误码

| 错误码 | 含义 |
|---|---|
| `INVALID_TRANSITION` | 非法状态转移 |
| `SUBTASK_VERIFY_FAILED` | 子任务校验失败（失败项重试 → 重拆 → FAILED；空计划亦用此码） |
| `SUBTASK_EXECUTION_FAILED` | 子任务执行未达成（循环失败态 / 执行异常归一，fail-closed，change 0126/0246） |
| `SUBTASK_TIMEOUT` | 子任务交接超时（`TaskHandoff.deadline`，change 0247）；取消子流后归一，进入重试/重拆 |
| `DEADLOOP_DETECTED` | 检测到死循环（触发重拆；预算耗尽转 FAILED） |
| `NO_AGENT_MATCH` | 无匹配子 Agent（抛错，调度器捕获并标记子任务失败） |
| `WAVE_FANOUT_LIMIT` | 并行度超限（同波次分批执行，受资源上限约束） |
| `INVALID_DISPATCH_POLICY` | 调度策略取值非法（构造器 fail-fast；change 0123） |
| `PROGRESS_NOT_MET` | 进度未达目标（触发重拆；预算耗尽转 FAILED） |
| `MISSING_SUCCESS_CHECKER` | 提供了成功标准但未注入判定器（配置错误，fail-fast，转 FAILED） |
| `TASK_CANCELLED` | 运行中任务被 `cancel` 取消（`task_failed` 终态，change 0249；断流同转 `FAILED`，trace `task_aborted` 分因） |
| `BACKGROUND_TASKS_FULL` | 运行中后台子 Agent 已达上限 8（`delegate(background=true)` 返回结构化失败，不排队；change 0270） |
| `TASK_TOKEN_BUDGET_EXCEEDED` | 整任务 token 预算耗尽（调度器累计；禁重试禁重拆，终态 FAILED，change 0280） |
| `TASK_TIMEOUT` | 整任务墙钟超时（**CLI `task` 入口**施加的 `asyncio.wait_for`；检查点保留，change 0280） |

> 失败恢复预算固定为「每个失败子任务重试 1 次 + 重新拆解 1 次」（change 0246 / ADR-0234），
> 不设配置键；`task_failed` 的 `attempts` / `replans` 为可观测计数。

---

## 5. 关联

- 模块：`02-modules/orchestration.md`
- 规格：`openspec/specs/orchestration/spec.md`
