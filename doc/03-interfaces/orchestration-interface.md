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
        planner: Planner | None = None,        # Callable[[str], list[Subtask] | Awaitable[...]]
        verifier: Verifier | None = None,      # Callable[[Subtask, Any], VerifyResult | Awaitable[...]]
    ) -> None: ...

    async def decompose(self, goal: str, success_criteria: list[str] | None = None) -> Plan:
        """大目标 → 分步 Todo（含验收标准与依赖 DAG）；success_criteria 透传至 Plan。

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
```

### 2.1 LLM 拆解 / 验收适配器

```python
class LLMSubtaskPlanner:
    """经 llm-provider acompletion 产子任务 DAG；失败/不可解析回落单子任务。"""
    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None: ...
    async def __call__(self, goal: str) -> list[Subtask]: ...

class LLMVerifier:
    """经 acompletion 对照 acceptance 判定结果；调用失败/不可解析 fail-closed。"""
    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None: ...
    async def __call__(self, subtask: Subtask, result: Any) -> VerifyResult: ...
```

- 拆解 prompt 约束输出 `{"subtasks": [{"id","goal","acceptance","depends_on","priority"}]}`；
  逐项校验（id/goal 非空、depends_on 引用已声明 id），非法项剔除，全非法则回落单子任务。
- 验收 prompt 输出 `{"passed": bool, "reason": str}`；解析失败按不通过处理（fail-closed）。

### 2.2 编排执行与进度事件

```python
class TaskScheduler:
    def __init__(self, ..., tracer: Tracer | None = None) -> None: ...

    async def run(
        self, task_id: str, goal: str, success_criteria: list[str] | None = None,
        *, plan: Plan | None = None, completed: set[str] | None = None,
        results: dict[str, str] | None = None,
    ) -> list[SubtaskOutcome]:
        """同步语义收口：消费 astream，终态失败按原错误码抛 OrchestrationError。
        plan/completed/results 为断点续跑注入面（跳过拆解与已完成子任务、
        重建依赖结果上下文）。"""

    def astream(self, task_id, goal, success_criteria=None, *, plan=None, completed=None,
        results=None
    ) -> AsyncIterator[LoopEvent]:
        """流式任务执行（进度事件）：task_started / plan_ready / wave_started /
        subtask_started / subtask_completed / task_checkpoint / task_finished /
        task_failed；关键节点（拆解/验收/检查点/终态）经 tracer 写 trace。"""
```

- CLI 入口：`core-agent task <目标> [--task-id ID | --resume ID]` 流式打印进度事件；
  `--resume` 从该 task-id 最新检查点重建 Plan 与已完成集，续跑未完成子任务；
  检查点经 CheckpointStore 落盘 `$CORE_STATE_DIR/checkpoints.jsonl`（缺省
  `~/.core/state/`），跨进程 kill/重启可续跑。
- 依赖结果交接：子任务验收通过的回复（截断 2000 字符）注入 `depends_on` 后继
  子任务的执行输入（「前置子任务结果」段），并随 `SubtaskOutcome.reply` 写入
  检查点 outcomes，续跑时经 `results` 参数重建依赖上下文。
- 事件复用 `core.loop.LoopEvent`（type + dict 载荷），与 loop/ui 事件面同构；
  载荷携带 UI 折叠详情所需字段：`subtask_started` 含 `goal` + `acceptance`（验收
  标准），`subtask_completed` 含 `reason`（判定）+ `reply` 节选（600 字符）。
- TUI 入口：REPL 会话内输入 `/task <目标>`，经 `UIAPILayer.run_task` 驱动同一编排器，
  进度事件以 `task.*` 前缀映射为 UI Event 流式呈现（与 CLI 同一格式化）。

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
```

---

## 4. 错误码

| 错误码 | 含义 |
|---|---|
| `INVALID_TRANSITION` | 非法状态转移 |
| `SUBTASK_VERIFY_FAILED` | 子任务校验失败（触发回退/重规划） |
| `DEADLOOP_DETECTED` | 检测到死循环（触发 RECOVERING） |
| `NO_AGENT_MATCH` | 无匹配子 Agent（抛错，调度器捕获并标记子任务失败） |
| `WAVE_FANOUT_LIMIT` | 并行度超限（同波次分批执行，受资源上限约束） |
| `PROGRESS_NOT_MET` | 进度未达目标（触发重试/重规划，衔接 RECOVERING） |
| `MISSING_SUCCESS_CHECKER` | 提供了成功标准但未注入判定器（配置错误，fail-fast，转 FAILED） |

---

## 5. 关联

- 模块：`02-modules/orchestration.md`
- 规格：`openspec/specs/orchestration/spec.md`
