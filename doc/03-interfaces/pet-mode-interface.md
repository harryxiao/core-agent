# 接口设计：宠物模式接口（Pet Mode Interface）

> 编排层扩展 ｜ 对应规格 `pet-mode/spec.md` ｜ 模块 `01-architecture/architecture-overview.md`（后台自治循环）

---

## 1. PetSession 生命周期接口

宠物会话是编排层「后台自治循环」的核心句柄：启动、休眠、恢复、异常退避、终止全生命周期由 `PetSession` 收口，每次唤醒复用 `Loop.run(user_input: str) -> LoopResult` 同步薄壳（asyncio.run 桥接）逐次执行，异常退避不残留半运行状态。

```python
class PetSessionState(Enum):
    IDLE = "idle"            # 未激活
    ACTIVE = "active"        # 激活运行中
    BACKOFF = "backoff"      # 异常退避（故障隔离，不残留半运行态）
    TERMINATED = "terminated"  # 已终止

class PetSession:
    session_id: str
    state: PetSessionState

    # 生命周期
    def start(self, task: PetTask) -> None: ...
    def wake(self) -> LoopResult: ...
        """每次唤醒经 Loop.run() 同步薄壳执行一次自治任务。"""

    def suspend(self) -> None: ...
        """让行/休眠：复用 orchestration 任务状态机 SUSPENDED，主循环 busy 时不抢锁。"""
    def resume(self) -> None: ...
        """主循环释放资源后恢复，已完成的子任务结果不丢失。"""
    def backoff(self, err: Exception) -> None: ...
        """异常退避：标记故障态、隔离，不阻塞主循环。"""
    def terminate(self) -> None: ...
        """终止释放：任务与资源释放，无悬空引用。"""

    # 任务派发
    def dispatch(self, task: PetTask) -> None: ...

    # 偏好追踪
    def observe(self, behavior: str) -> MemoryEntry: ...
        """观察主人行为/反馈，以 MemoryEntry.source="user" 落 L2 facts 层。"""
    def prefer(self, key: str) -> str | None: ...
        """复用已记录偏好，供任务执行/沟通时对齐主人偏好。"""

    # 反馈与惊喜
    def report(self) -> str: ...
        """达到反馈周期时向主人汇报后台进展，不阻塞主循环。"""
    def surprise(self) -> str: ...
        """基于主人偏好发现可代办/取悦之事，主动执行并制造惊喜。"""
```

> 让行/休眠不新增枚举：复用 orchestration 任务状态机 `SUSPENDED`（宿主 loop 状态），宠物自身会话态仅 `IDLE / ACTIVE / BACKOFF / TERMINATED` 四态。

---

## 2. Persona 人格与随机任务开关（pet.md）

每只宠物经 `pet.md`（目录 `pet.persons_dir`，每只一个 `<name>.md`）声明人格；人格经 `PersonaLayer.render_prompt()` 渲染进自主任务提示词，宠物行为/输出风格受其约束（R9）。随机微任务可配置关闭（R14）。

```python
@dataclass
class Persona:              # 实现 PersonaLayer
    name: str               # 角色名
    species: str            # 物种
    persona_text: str       # 性格描述（角色/性格）
    traits: list[str]       # 性格特征
    preferences: list[str]  # 喜好

    def render_prompt(self) -> str: ...
        """组合 pet.md 人格为 persona 提示词，宠物行为/输出风格受其约束。"""
```

| 字段 | 语义 | 契约 Requirement |
|---|---|---|
| 角色 `name` | 宠物角色名 | R9 Pet Persona and Prompt |
| 性格 `persona_text` + `traits` | 性格描述与特征 | R9 |
| 喜好 `preferences` | 主人/宠物偏好 | R9 |
| 随机任务开关 | 日常随机微任务开关；侵入性（无厘头注释）默认关 | R14 Pet Micro-tasks |

---

## 3. PetTask 任务类型

宠物会话只承载重复简单任务，任务类型枚举收口为两类：

```python
class PetTaskKind(Enum):
    INFORMATION_GATHERING = "information_gathering"  # 信息收集
    IDLE_EXPLORATION = "idle_exploration"            # 闲逛探索

@dataclass
class PetTask:
    kind: PetTaskKind
    goal: str          # 任务目标描述（Agent 可理解的自然语言）
    priority: int = 0  # 固定低优先级，让行主循环
```

---

## 4. 三入口激活契约

三入口统一走「pet session 生命周期」契约收口，避免各自实现激活逻辑产生第二真源：

| 入口 | 触发 | 桥接方式 | 落点 |
|---|---|---|---|
| `/pet` 斜杠命令 | UI 层命令面板 | plugin-registry 注册的 command/tool 元数据经统一 API `UIAPILayer.list_tools()` 拉取候选，不进内核接口 | ui-interface.md |
| `pet <verb>` CLI argv | 宿主 CLI 命令 | cli-ops-interface `CommandGroup` 扩展，解析 argv | cli-ops-interface.md |
| WebUI 自然语言 | 「启动宠物 + 任务」 | 经 `UIAPILayer.run_loop()` / `IMGateway.on_message` 消息驱动会话，激活靠 Agent 理解意图 | ui-interface.md / im-interface.md |

```python
# 三入口最终都落到同一 PetSession 生命周期
class PetActivator:
    def activate_from_slash(self, tool_id: str) -> PetSession: ...
        """`/pet` 候选来自 UIAPILayer.list_tools()，不进内核接口。"""
    def activate_from_cli(self, verb: str, rest: list[str]) -> PetSession: ...
        """cli-ops-interface CommandGroup 扩展的 argv 解析。"""
    def activate_from_nl(self, user_input: str) -> PetSession: ...
        """WebUI 自然语言经 UIAPILayer.run_loop()/IMGateway.on_message，Agent 理解后绑定任务。"""
```

---

## 5. 宠物循环契约（后台自治循环）

主循环之上叠加后台自治调度：任务派发 → 周期触发 → 偏好读写 → 反馈/惊喜 → 让行退避。

| 环节 | 契约 | 说明 |
|---|---|---|
| 任务派发 | `dispatch(task)` | 低优先级派发，主循环 busy 时让行，不抢锁 |
| 周期触发 | `wake()` | 每次唤醒复用 `Loop.run()` 同步薄壳，逐次执行不常驻 |
| 偏好读写 | `observe()` / `prefer()` | 以 `MemoryEntry.source="user"` 落 L2 facts，不新造记忆层 |
| 反馈 | `report()` | 达到周期向主人汇报，不阻塞主循环 |
| 惊喜 | `surprise()` | 基于主人偏好代办/取悦，结果反馈主人 |
| 让行退避 | `suspend()` / `backoff()` | 让行复用 orchestration `SUSPENDED`；异常退避为 `BACKOFF` 故障隔离 |

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `PET_ALREADY_ACTIVE` | 会话已激活，重复激活被拒 |
| `PET_NOT_ACTIVE` | 会话未激活，唤醒/派发/恢复无效 |
| `PET_BACKOFF` | 会话处于异常退避态，暂不可唤醒 |
| `PET_YIELDING` | 主循环 busy，宠物让行（复用 orchestration `SUSPENDED`） |
| `PET_PREFERENCE_WRITE_FAILED` | 偏好写入 L2 facts 层失败 |

---

## 7. 关联

- 规格：`openspec/specs/pet-mode/spec.md`
- 变更：`openspec/changes/0030-pet-mode/`
- 模块：`01-architecture/architecture-overview.md`
- 复用接口：`loop-interface.md`（`Loop.run` 同步薄壳）、`ui-interface.md`（`UIAPILayer.list_tools/run_loop`）、`im-interface.md`（`IMGateway.on_message`）、`cli-ops-interface.md`（`CommandGroup`）、`memory-interface.md`（`MemoryEntry.source`）、`orchestration-interface.md`（任务状态机 `SUSPENDED`）
