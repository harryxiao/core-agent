# 模块设计：宠物模式（Pet Mode）

> 对应规格：`doc/openspec/specs/pet-mode/spec.md` ｜ 接口：`doc/03-interfaces/pet-mode-interface.md`
> 定位：**后台自治循环扩展**，以统一 pet session 生命周期承载重复简单任务（信息收集 / 闲逛探索）、偏好追踪、定期反馈/惊喜，低优先级让行不阻塞主循环。

---

## 1. 模块定位

pet-mode 为 core-agent 提供后台自治循环扩展与宿主层三入口交互面：以统一 pet session 生命周期承载重复简单任务、偏好追踪、定期反馈/惊喜，低优先级让行不阻塞主循环，三入口激活后台宠物会话——相当于"人类养宠物"，做当前不太重要的事、了解主人偏好、制造惊喜。

本模块是编排层的**后台**自治扩展，与 beast-mode 的**前台**重大任务正交：pet 做"低优先级、可让行"的重复简单事，不抢主循环。

---

## 2. 内部组成

```
PetMode（后台自治循环扩展）
├── PetSession     会话句柄：IDLE / ACTIVE / BACKOFF / TERMINATED 四态（含 snapshot/restore）
├── Persona        宠物人设：dataclass + render_prompt()
├── PetTask        任务载体：PetTaskKind（INFORMATION_GATHERING / IDLE_EXPLORATION）
├── PetManager     多宠物注册表：独立启停 + 故障隔离（可选落盘，跨进程存活）
├── PetActivator   三入口激活：/pet 斜杠 / pet <verb> CLI / WebUI 自然语言（注入 loop/记忆/探索/安全/通知）
└── PetControl     控制面门面：verb(status/sleep/wake/assign/stop) → 会话操作 + 寻址（CLI 与 UIAPILayer 共用）
```

---

## 3. 关键设计

### 3.1 会话生命周期

- 宠物会话以 `PetSessionState` 四态（IDLE / ACTIVE / BACKOFF / TERMINATED）管理启动、休眠、恢复、异常退避、终止全生命周期。
- 每次唤醒复用 **统一交接执行器** `handoff.run_handoff`（`asyncio.run` 桥接，change `0247`／ADR-0235）
  逐次执行；宠物传空上下文 + 自身 `session_id` ⇒ `render_handoff` 逐字返回任务文本，loop prompt
  与改造前一致。异常退避不残留半运行状态。

### 3.2 低优先级让行

- 宠物会话低优先级运行：主循环 busy 时 `suspend()` 让行，复用编排层任务状态机 `SUSPENDED`；异常退避为 `BACKOFF` 故障隔离。
- 周期触发每次唤醒复用 `Loop.run()`，逐次执行不常驻；`dispatch(task)` 派发时主循环 busy 则让行，不抢锁。
  **唤醒由宿主驱动**（内核只提供同步薄壳 `wake()`，不自建调度线程 —— change `0065`，账本 E17 关闭）：
  规格无 daemon 条款（让行模型为「同步 + 锁」），且 `pet <verb>` 是一次性进程，进程内线程必随进程结束。

### 3.3 偏好追踪

- `observe()` 观察主人行为/反馈，以 `MemoryEntry.source="user"` 落 L2 facts 层，**不新造记忆层**；`prefer()` 复用已记录偏好，供任务执行/沟通时对齐主人。
- 偏好复用既有 memory 闭环，与"记忆即光谱"一致。
- **轨迹命名空间**：宠物专属 loop 的 `DefaultLoop(source="pet")` ⇒ 自治轨迹落独立命名空间（`source=pet`），主侧装配器封存、宠物自身经**派生**装配器放行（见 `03-interfaces/pet-mode-interface.md` §1）—— `source` 划 Agent 身份、`session_id` 划会话个体，二维并行（change `0118`／ADR-0111）。

### 3.4 三入口激活

- 三入口统一落 `PetActivator`：`/pet` 斜杠命令、`pet <verb>` CLI argv、WebUI 自然语言。
- 激活后进入 pet session 生命周期，会话句柄唯一收口，入口只做激活不管理状态。

### 3.5 反馈与惊喜

- `report()` 达到周期向主人汇报，不阻塞主循环；`surprise()` 基于主人偏好经**真实 loop** 代办/取悦并回报**真实产出**，无偏好 ⇒ `None`（不谎报）。
- 二者均为"后台自治"的价值输出，服务偏好追踪闭环。
- **通知投递（change `0079`／ADR-0076，账本 E16）**：`wake()` 收尾在反馈周期命中时经通知器把 `report()` 产出**真的投出去**（`notify` 入队 → 组合根收口 flush，不阻塞主循环）；缺省通道 = stderr 一行，真实 IM 通道由宿主注入替换。
- **安全强制执行（change `0081`／ADR-0077，账本 E25）**：`Explorer` 白名单成为宠物专属 `ToolProvider`
  的注册面（R11），`SafetyBounds` 经安全中间件挂在专属 loop 的 before 接缝（R12）；越界 ⇒ 本轮终止 +
  通知主人，会话保持 `ACTIVE`（见 §4 生产装配）。
- **惊喜上报（change `0086`／ADR-0081，账本 E26 的 surprise 半边）**：`surprise()` 已接线 —— 唤醒收尾与周期反馈
  **同节拍**尝试，有偏好 ⇒ 跑一次 loop 真实代办、回报真实产出，无偏好 ⇒ 不产出不投递（消灭「已帮你安排」谎报）；
  惊喜失败 fail-soft，不阻断唤醒。
- **微任务真实化与空闲自治睡眠（change `0087`／ADR-0082，账本 E26 的 microtask 半边）**：`MicrotaskRunner`
  已接线 —— 三条任务各取**真实来源**（`terminal_walk` 读命令历史**只报条数**、绝不外泄内容；`system_hint` 真探负载、
  不显著则不出声；`nonsense_comment` 仅在注入写回口时真写），**无真实产出 ⇒ `None`**（投出即谎报，与 `0086` 同口径）。
  `wake()` 改为**消费队首任务**（一次性）；队列清空 ⇒ 会话进入**休眠**（让行态，不新增枚举、不编造任务），
  入睡前（有通知面时）触发一次微任务并上报真实产出；**新任务派发 ⇒ 自动唤醒**。宿主驱动（§3.6）**零改动**
  —— 入睡后唤醒抛 `PET_YIELDING`，驱动按既有预期态 `skipped` 跳过。

### 3.6 宿主驱动（`pet run`，change `0083`／ADR-0078，账本 E28）

- **驱动者 = 用户显式启动的前台常驻进程**：`core-agent pet run [--interval S]`（缺省 60s）按间隔逐会话
  `wake()` —— `0065` 裁决「内核不自建 daemon」的**宿主侧落地**（非内核偷起线程，而是宿主显式常驻）；
  也不做「开 WebUI 就后台唤醒」的隐式副作用（无 UI 的部署同样要能驱动）。
- `PetWakeDriver(sessions, *, sleep=time.sleep)`：`sessions` 是**可调用体**（`PetManager.list`），
  每轮重取 ⇒ 驱动期间新注册的宠物自动纳入；`tick()` 返回结构化 `WakeOutcome`（库层不打印，呈现归 CLI）；
  `sleep` 可注入 ⇒ 节拍测试确定性（先例：`0052` 给 `CircuitBreaker` 注入 `clock`）。
- **故障隔离**（规格 R8）：让行/退避/未激活（`PetError`）= 预期态**静默跳过**（让行是设计中的常态，
  逐轮刷屏即噪音）；意外异常 ⇒ `failed` 记因并**继续其余宠物**；无注册会话 ⇒ 提示激活入口、退出 0
  （**不自动造宠物** —— 激活归三入口）。
- `--interval` 是**宿主命令的运行参数**（同 `ui serve --host/--port`），**不进 `ConfigSpec`**。

### 3.7 控制面（`PetControl`，change `0088`／ADR-0083）

- **单一门面**：控制动词有**两个宿主面**（CLI `pet <verb>`、`UIAPILayer.pet_command`）。若各自分发就是两份真源，
  故 `PetControl` 收口「verb → 会话操作 + 寻址」，两个宿主都只调用它。门面**无状态**（只持 `PetManager`），
  构造廉价 ⇒ 组合根就地构造，**不给 `Runtime` 加字段**。
- **只复用既有操作**：`sleep→suspend`、`wake→resume`、`assign→dispatch`、`stop→PetManager.stop`、`status→snapshot` 过滤。
  **不新增 `PetSession` 公开 API**（`snapshot()` 已有；不读私有）。
- **寻址不猜**：单宠物默认、多宠物未指定 ⇒ `PET_TARGET_AMBIGUOUS` 列出 id、未知 ⇒ `PET_NOT_FOUND`（不静默成功）。
- **观测面不外泄**：`status` 过滤掉 `preferences` 与任务正文（对齐「密钥只引用不读取」的隐私取向）。
- **作用域 = 本进程**：跨进程注册表是快照，不驱动 live 会话 —— **有意不做**跨进程（用户裁决「仅同进程」）。

---

---

## 4. 后台自治闭环

```
三入口激活 ──PetActivator──► PetSession（IDLE → ACTIVE）
每次唤醒 ──Loop.run() 同步薄壳──► 消费队首任务、执行一次（信息收集 / 闲逛探索）
观察行为 ──observe()──► MemoryEntry.source="user" 落 L2 facts
周期 ──report()/surprise()──► 向主人汇报 / 制造惊喜
队列清空 ──_go_idle()──► 入睡（让行态）+ 触发一次微任务并上报真实产出
新任务 ──dispatch()──► 自动唤醒（清让行态）
主循环 busy ──suspend()/backoff()──► 让行（复用 SUSPENDED）/ 异常退避（BACKOFF）
```

- 任务执行、偏好沉淀、反馈惊喜都回到既有 loop/memory 闭环，pet 只做"低优先级编排扩展"，不另起炉灶。
- 闭环的**驱动者是宿主**：「每次唤醒」这一环由宿主入口（或长驻宿主）按自身周期调用 `wake()`，内核只保证
  单次唤醒是同步薄壳、不常驻、可让行（change `0065` 登记为已知语义，非缺失）。
  该职责的**宿主侧落地**（change `0083`／ADR-0078，账本 E28）：`core-agent pet run [--interval S]`
  前台常驻，经 `PetWakeDriver` 逐会话唤醒（详见 §3.6）。
- **生产装配**（change `0053`）：pet 依赖由组合根 `build_runtime` 组装 —— 一份 `Explorer`/`SafetyBounds`/`AsyncNotifier`
  + `PetManager`（落盘 `$CORE_STATE_DIR/pets.json`）+ `PetActivator`（注入**宠物专属 loop**（受限工具集 +
  安全中间件，change `0081`）与 runtime 共享 memory）；
  `Runtime.pet_manager`/`pet_activator` 供 `entry._pet`（CLI）与 `UIAPILayer.activate_pet`（WebUI）共用，
  缺省（无组合根）仍走 echo loop 兜底、行为不变。
- **门控**（change `0067`，账本 E10）：`features.pet: false` 时 pet **完全不装配** —— 不构造
  `PetManager`（**不读** `pets.json`）、`Runtime.pet_manager`/`pet_activator` 为空、`pet` CLI 与
  WebUI 入口一并拒绝。**两级开关各管各的**：`features.pet` 管**装配**（缺省开），`pet.enabled`
  管**启用**（缺省关，`ConfigSpec` 单一真源）；前者关时后者无意义，前者开而后者关即今日形态。

---

## 5. 错误处理

| 错误码 | 含义 |
|---|---|
| `PET_ALREADY_ACTIVE` | 会话已激活，重复激活被拒 |
| `PET_NOT_ACTIVE` | 会话未激活，唤醒/派发/恢复无效 |
| `PET_BACKOFF` | 会话处于异常退避态，暂不可唤醒 |
| `PET_YIELDING` | 主循环 busy，宠物让行（复用 orchestration `SUSPENDED`） |
| `PET_NOT_FOUND` | 控制面指定的会话 id 未注册（change `0088`） |
| `PET_TARGET_AMBIGUOUS` | 控制面未指定会话但注册多只宠物（拒绝并列出 id） |
| `PET_PREFERENCE_WRITE_FAILED` | 偏好写入 L2 facts 层失败 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/pet-mode-interface.md`
- 规格：`doc/openspec/specs/pet-mode/spec.md`
- 复用接口：`loop-interface.md`（`Loop.run` 同步薄壳）、`ui-interface.md`、`im-interface.md`、`cli-ops-interface.md`、`memory-interface.md`（`MemoryEntry.source`）、`orchestration-interface.md`（任务状态机 `SUSPENDED`）
- 对偶：`doc/02-modules/beast-mode.md`（前台重大任务）
- 组合根：`src/core/runtime.py`（装配 pet 依赖 + `_pet_state_path`）；ADR-0056
