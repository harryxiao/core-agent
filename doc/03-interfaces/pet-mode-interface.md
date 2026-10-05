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
        """每次唤醒**消费队首任务**经 Loop.run() 同步薄壳执行一次；队列清空 ⇒ 入睡（让行态）。"""

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
        """低优先级派发；**新任务自动唤醒**让行/休眠中的宠物（清让行态）。"""

    # 偏好追踪
    def observe(self, behavior: str) -> MemoryEntry: ...
        """观察主人行为/反馈，以 MemoryEntry.source="user" 落 L2 facts 层；
        记忆后端未接 / 写入失败抛 PET_PREFERENCE_WRITE_FAILED（**库层直接调用面**，异常不吞）。"""
    def observe_owner(self, text: str) -> MemoryEntry | None: ...
        """**生产入口**观察主人原话：非空即转 observe，失败静默跳过（fail-soft，不阻断激活/派发）；
        空文本（无主人原话）⇒ None 不写入（spec R7：不以通用文案谎报偏好）。"""
    def prefer(self, key: str) -> str | None: ...
        """复用已记录偏好，供任务执行/沟通时对齐主人偏好。"""

    # 反馈与惊喜
    def report(self) -> str: ...
        """达到反馈周期时向主人汇报后台进展，不阻塞主循环。"""
    def surprise(self) -> str | None: ...
        """基于主人偏好经**真实 loop** 代办/取悦；无偏好（无真实可代办前提）⇒ None（不谎报）。"""
```

> 让行/休眠不新增枚举：复用 orchestration 任务状态机 `SUSPENDED`（宿主 loop 状态），宠物自身会话态仅 `IDLE / ACTIVE / BACKOFF / TERMINATED` 四态。
>
> **任务一次性与空闲入睡（change `0087`／ADR-0082，账本 E26）**：`wake()` **消费**队首任务（`popleft`，任务一次性）；
> 队列清空 ⇒ 会话进入休眠（置让行态，**不新增枚举、不编造任务**），后续唤醒以 `PET_YIELDING` 拒绝（宿主驱动 `pet run` 天然按预期态跳过）；
> **新任务派发 ⇒ 自动唤醒**（`dispatch()` 清让行态）。入睡前（**有通知面**时）触发一次微任务并上报其**真实产出**。

> **依赖注入与快照**（change `0053`）：`loop`/记忆/探索/安全/通知依赖由组合根（`build_runtime`）经 `PetActivator` 注入，
> 生产激活的宠物因此持有 runtime 的真实 loop、共享记忆后端与 `MicrotaskRunner`（偏好落 L2、唤醒走真 loop、空闲跑真微任务）。`snapshot()` / `restore(record, **deps)`
> 支持会话快照与恢复（注册表落盘用）；缺省依赖全 `None` → echo loop / 无记忆兜底，行为不变。
> **通知接线（change `0079`／ADR-0076，账本 E16）**：通知器此前只注入不投递（`_notifier` 零调用、`AsyncNotifier` 无 channel、`flush()` 零调用方）。现已三环连通 —— 生产者落 `wake()` 收尾（反馈周期命中时投递 `report()` 产出），缺省通道 = stderr 一行（主人可见的观测面），投递点由组合根收成单一可调用体（入队后即 flush）注入；真实 IM 通道仍由宿主注入替换。
>
> **偏好追踪接线（change `0110`／ADR-0103，账本 E39）**：`observe` 此前**零生产调用方**（`_preferences` 恒空、
> `surprise()` 恒 `None`）。现经 `observe_owner` 接在**主人原话入口**三处：`PetActivator.activate_from_cli`（`rest`）、
> `activate_from_nl`（`user_input`）、`PetControl.assign`（`goal`）。**不在 `wake()` 内 observe** ——
> 唤醒时宠物只在跑自己的任务，无主人行为可观察；且 `/pet` 斜杠激活与空 `rest` 的 goal 是**合成文案**
> （`斜杠命令 pet.gather` / `CLI 命令 gather`），观察它等于谎报偏好（spec R7 明禁）⇒ 二者**零写入**。

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

> **生产装配**（change `0053`）：三入口由组合根产出的 `Runtime.pet_activator` 驱动 —— CLI 经 `entry._pet`（`pet <verb>`）、
> WebUI 经 `UIAPILayer.activate_pet(user_input) -> session_id`；`/pet` 斜杠面板在 UI 层（候选来自 `list_tools`），不进内核。
> `PetManager` 经 `Runtime.pet_manager` 共享并落盘 `$CORE_STATE_DIR/pets.json`（注册表跨进程存活）。
> **门控（change `0067`）**：`features.pet: false` ⇒ 以上三入口一并不可用（组合根不产出
> `pet_manager`/`pet_activator`，CLI 报「pet 模块已关闭」、WebUI 报「宠物激活器未接」）。

---

## 5. 宠物循环契约（后台自治循环）

主循环之上叠加后台自治调度：任务派发 → 周期触发 → 偏好读写 → 反馈/惊喜 → 让行退避。

| 环节 | 契约 | 说明 |
|---|---|---|
| 任务派发 | `dispatch(task)` | 低优先级派发，主循环 busy 时让行，不抢锁；**新任务自动唤醒**让行/休眠中的宠物（change `0087`） |
| 周期触发 | `wake()` | 每次唤醒复用 `Loop.run()` 同步薄壳，逐次执行不常驻；**消费队首任务**（change `0087`） |
| 偏好读写 | `observe()` / `prefer()` | 以 `MemoryEntry.source="user"` 落 L2 facts，不新造记忆层 |
| 反馈 | `report()` | 达到周期向主人汇报，不阻塞主循环；**唤醒收尾经通知器投递**（change `0079`） |
| 惊喜 | `surprise()` | 有偏好 ⇒ 经真实 loop 代办并回报真实产出；无偏好 ⇒ `None`（不谎报）。**唤醒收尾同反馈节拍投递**，失败 fail-soft（change `0086`／ADR-0081，账本 E26） |
| 空闲/微任务 | `_go_idle()` + `microtasks()` | 队列清空 ⇒ 入睡（让行态）；有通知面时触发一次微任务并上报**真实产出**，无产出不谎报（change `0087`／ADR-0082） |
| 让行退避 | `suspend()` / `backoff()` | 让行复用 orchestration `SUSPENDED`；异常退避为 `BACKOFF` 故障隔离 |

> **驱动归属：「周期触发」由宿主驱动，内核不常驻、不自建调度线程（change `0065`，账本 E17 关闭）**。
> `PetSession` 只提供 `wake()`（`Loop.run()` 同步薄壳，**逐次执行、不常驻**）；**谁按周期调用它由宿主决定**
> —— 即激活该会话的宿主入口（`pet <verb>` / `/pet` / WebUI 自然语言）或将来某个常驻宿主。
> 内核**不**内置 daemon，三条理由：① pet-mode 规格的让行模型是「**同步 + 锁（RLock）**，宠物让行不抢锁」，
> 全篇**无 daemon / 调度线程条款**（唤醒语义按「每次唤醒…逐次执行」表述，驱动者不在规格内）；
> ② `core-agent pet <verb>` 是**一次性进程**（激活 → 打印 → 退出），进程内线程必随进程结束 —— 在那里 daemon 化
> 是**错误解法**；③ 能承载常驻驱动的是**长驻宿主**：`core-agent ui` 的 `serve()`，或 change `0083` 起的 `core-agent pet run [--interval S]`（前台常驻、显式启动、无 UI 依赖 —— 见 §5.2）。故「后台自治调度」是**宿主职责**，
> 是否常驻由宿主自选（`wake()` 的同步薄壳形态对两种宿主都成立）。

### 5.1 安全边界与受限探索工具集（change `0081`，账本 E25）

规格 R11「Exploration Toolset」/ R12「Pet Safety Bounds」/「Pet Session Runtime Wiring」均明文要求**强制**；
change `0081` 之前二者只注入不消费，且宠物**跑在主 loop 上**（一次唤醒可调用全部工具），边界无一处在路径上。
现宠物持有**专属 loop**，两条款各由一处机制落地：

| 条款 | 机制 | 落地方式 |
|---|---|---|
| R11 受限探索工具集 | `Explorer.available()` = **白名单真源** | 组合根只把白名单内的真实工具注册进宠物的 `ToolProvider`（缺省 `{"tools.file_read"}`）——未注册即 loop 结构化拒绝（fail-closed by construction），且模型**看不到**越界工具 |
| R12 安全边界 | `SafetyBounds.check(op, target)` | 经 `build_safety_middleware` 挂到专属 loop 的 before 接缝（`middlewares=`），越界 ⇒ **终止 Action** |

- **判定顺序**：不可逆 → 只读优先 → 爆炸半径（先判最不可逆的）。
  - **不可逆**（缺省 `tools.file_write` / `file_patch` / `code_run` / `install` / `uninstall`）恒禁止；
  - **只读优先**（`readonly=True` 缺省）：白名单外操作一律越界 —— 判据是**只读白名单**（`readonly_ops`），
    不是 `read` 前缀启发式（真实 id 无此前缀，启发式必然失效）；
  - **爆炸半径**：`allowed_prefixes` 与 `target` **均非空**时才判定（target 从 `args` 的
    `path`/`file`/`url`/`target` 首个命中键取，取不到即不判半径）；组合根缺省 `[Path.cwd()]`（宠物只在
    启动目录内探索）。三个集合/清单**构造面可注入**替换缺省，不新增配置键。
- **「越界即暂停」的实现口径**（规格 MODIFIED 钉死）：越界动作**不执行**，本轮**终止**
  （返回终止 Action `{"reply": …}`，与 loop 既有 `decline()` 路径同构 —— 无需新增 loop 语义），并**通知主人**
  （含越界原因；经 `wake()` 通知器，见 §5「反馈」行 / ADR-0076）。**会话保持 `ACTIVE`**
  —— 不调 `suspend()`：生产无任何 `resume()` 调用方，转 yielding 即**永久楔死**。
- **宠物不共享主 loop 的熔断链**：专属 loop 只挂安全中间件（宠物流量不应污染主线熔断态）。

### 5.2 宿主驱动（`pet run`，change `0083`，账本 E28）

「周期触发由宿主驱动」（change `0065`）的**宿主侧落地**：`core-agent pet run [--interval S]` 前台常驻，
按间隔逐会话 `wake()`。

| 环节 | 契约 | 说明 |
|---|---|---|
| 驱动者 | 用户**显式启动**的前台进程 | 内核**不**自建 daemon；**不做**「开 WebUI 就后台唤醒」的隐式副作用（宠物唤醒会真调 LLM / 真跑工具） |
| 节拍 | `PetWakeDriver(sessions, *, sleep=…).tick() / .run(interval, on_tick=…)` | `sessions` 是**可调用体**（`PetManager.list`），每轮**重取** ⇒ 驱动期间新注册的宠物自动纳入；`sleep` 可注入 ⇒ 节拍可确定性测试 |
| 间隔 | `--interval S`（缺省 60s，须为正数） | **宿主命令的运行参数**（同 `ui serve --host/--port`），**不进 `ConfigSpec`**；非法/非正 ⇒ 用法错误退出 1 |
| 恢复 | 跨进程注册表 `pets.json`（change `0053`） | 新进程读回 `ACTIVE` 会话（任务队列 / 唤醒计数）继续驱动 |
| 故障隔离 | `WakeOutcome.status ∈ {woken, skipped, failed}` | 让行/退避/未激活（`PetError`）= **预期态静默跳过**；意外异常 ⇒ `failed` 记因并**继续其余宠物**（规格 R8「A 宠物异常不影响 B 宠物」） |
| 空注册表 | 提示三入口激活 + 退出 0 | **不自动造宠物**（激活归三入口，避免第二真源） |

### 5.3 控制面（`PetControl`，change `0088`，用户诉求①）

前台（`/pet [cmd]`、`pet <verb>` CLI argv、WebUI 自然语言）在宠物运行期间**随时**查看状态 / 让它
停止工作 / 换一件活 / 睡觉 / 叫醒。控制面由**单一门面** `PetControl`（`src/core/pet/core/control.py`）
收口 —— CLI 与 `UIAPILayer` 都只**调用它**，**不各自实现** verb 分发（避免两份真源）。

| 动词 | 落到 | 说明 |
|---|---|---|
| `status` | `snapshot()` 过滤 | 结构化 `session_id` / `state` / `sleeping`(=yielding) / `pending` / `wake_count` / `fault`；**不含**主人偏好与任务正文 |
| `sleep` | `PetSession.suspend()` | 置让行态（休眠）；后续 `PetSession.wake()` 以 `PET_YIELDING` 拒绝 |
| `wake` | `PetSession.resume()` | **清让行态恢复**。**命名陷阱**：与 `PetSession.wake()`（执行一次任务）语义不同，见 ADR-0083 |
| `assign` | `dispatch()` | 换活：入队新任务并清让行态（自动唤醒，change `0087`） |
| `stop` | `PetManager.stop()` | 终止会话并释放 |

**寻址**（`_resolve`）：显式 `--session ID` / `session_id=` ⇒ 按 id 取；**未指定且仅注册一只** ⇒ 默认作用于它；
**未指定且多只** ⇒ `PET_TARGET_AMBIGUOUS` 并**列出可选 id**（不猜测）；**指定但未注册** ⇒ `PET_NOT_FOUND`
（CLI 退出码 1，不静默成功 —— 对照 `PetManager.stop()` 注入式批量驱动的静默容错取向）。

**作用域 = 本进程已注册会话**：`PetManager.list()` 返回本进程内存，另一进程 `pet run` 常驻驱动**不重读**注册表
⇒ 跨进程控制今天不通，**有意不做**（避免「改了盘却没驱到 live 会话」的假象）。将来若做跨进程，`PetControl` 是唯一扩展点。

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `PET_ALREADY_ACTIVE` | 会话已激活，重复激活被拒 |
| `PET_NOT_ACTIVE` | 会话未激活，唤醒/派发/恢复无效 |
| `PET_BACKOFF` | 会话处于异常退避态，暂不可唤醒 |
| `PET_YIELDING` | 主循环 busy 让行 / 队列清空休眠（均复用 orchestration `SUSPENDED`） |
| `PET_NOT_FOUND` | 控制面指定的会话 id 未注册（change `0088`；CLI 退出码 1） |
| `PET_TARGET_AMBIGUOUS` | 控制面未指定会话但注册多只宠物（拒绝并列出可选 id，不猜测） |
| `PET_PREFERENCE_WRITE_FAILED` | 偏好写入 L2 facts 层失败 |

---

## 7. 关联

- 规格：`openspec/specs/pet-mode/spec.md`
- 变更：`openspec/changes/0030-pet-mode/`
- 模块：`01-architecture/architecture-overview.md`
- 控制面：`ui-interface.md`（`UIAPILayer.pet_command`）、`ADR-0083`
- 复用接口：`loop-interface.md`（`Loop.run` 同步薄壳）、`ui-interface.md`（`UIAPILayer.list_tools/run_loop`）、`im-interface.md`（`IMGateway.on_message`）、`cli-ops-interface.md`（`CommandGroup`）、`memory-interface.md`（`MemoryEntry.source`）、`orchestration-interface.md`（任务状态机 `SUSPENDED`）
