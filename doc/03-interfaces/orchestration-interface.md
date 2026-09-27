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
    def decompose(self, goal: str) -> Plan:
        """大目标 → 分步 Todo（含验收标准与依赖 DAG）。"""

    def verify(self, subtask: Subtask, result: Any) -> VerifyResult:
        """用验收标准校验子任务结果；通过才推进。"""

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

class MultiAgentRouter:
    def match(self, task: str) -> AgentProfile | None:
        """按任务类型匹配最合适子 Agent；无匹配返回 None。"""

    def handoff(self, target: str, h: TaskHandoff) -> str:
        """交接任务；返回子任务执行 trace_id。"""
```

---

## 4. 错误码

| 错误码 | 含义 |
|---|---|
| `INVALID_TRANSITION` | 非法状态转移 |
| `SUBTASK_VERIFY_FAILED` | 子任务校验失败（触发回退/重规划） |
| `DEADLOOP_DETECTED` | 检测到死循环（触发 RECOVERING） |
| `NO_AGENT_MATCH` | 无匹配子 Agent（降级/转人工） |
| `WAVE_FANOUT_LIMIT` | 并行度超限（同波次分批执行，受资源上限约束） |
| `PROGRESS_NOT_MET` | 进度未达目标（触发重试/重规划，衔接 RECOVERING） |

---

## 5. 关联

- 模块：`02-modules/orchestration.md`
- 规格：`openspec/specs/orchestration/spec.md`
