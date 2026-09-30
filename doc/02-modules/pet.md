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
├── PetSession     会话句柄：IDLE / ACTIVE / BACKOFF / TERMINATED 四态
├── Persona        宠物人设：dataclass + render_prompt()
├── PetTask        任务载体：PetTaskKind（INFORMATION_GATHERING / IDLE_EXPLORATION）
└── PetActivator   三入口激活：/pet 斜杠 / pet <verb> CLI / WebUI 自然语言
```

---

## 3. 关键设计

### 3.1 会话生命周期

- 宠物会话以 `PetSessionState` 四态（IDLE / ACTIVE / BACKOFF / TERMINATED）管理启动、休眠、恢复、异常退避、终止全生命周期。
- 每次唤醒复用 `Loop.run()` 同步薄壳（asyncio.run 桥接）逐次执行，异常退避不残留半运行状态。

### 3.2 低优先级让行

- 宠物会话低优先级运行：主循环 busy 时 `suspend()` 让行，复用编排层任务状态机 `SUSPENDED`；异常退避为 `BACKOFF` 故障隔离。
- 周期触发每次唤醒复用 `Loop.run()`，逐次执行不常驻；`dispatch(task)` 派发时主循环 busy 则让行，不抢锁。

### 3.3 偏好追踪

- `observe()` 观察主人行为/反馈，以 `MemoryEntry.source="user"` 落 L2 facts 层，**不新造记忆层**；`prefer()` 复用已记录偏好，供任务执行/沟通时对齐主人。
- 偏好复用既有 memory 闭环，与"记忆即光谱"一致。

### 3.4 三入口激活

- 三入口统一落 `PetActivator`：`/pet` 斜杠命令、`pet <verb>` CLI argv、WebUI 自然语言。
- 激活后进入 pet session 生命周期，会话句柄唯一收口，入口只做激活不管理状态。

### 3.5 反馈与惊喜

- `report()` 达到周期向主人汇报，不阻塞主循环；`surprise()` 基于主人偏好代办/取悦，结果反馈主人。
- 二者均为"后台自治"的价值输出，服务偏好追踪闭环。

---

## 4. 后台自治闭环

```
三入口激活 ──PetActivator──► PetSession（IDLE → ACTIVE）
每次唤醒 ──Loop.run() 同步薄壳──► 执行一次自治任务（信息收集 / 闲逛探索）
观察行为 ──observe()──► MemoryEntry.source="user" 落 L2 facts
周期 ──report()/surprise()──► 向主人汇报 / 制造惊喜
主循环 busy ──suspend()/backoff()──► 让行（复用 SUSPENDED）/ 异常退避（BACKOFF）
```

- 任务执行、偏好沉淀、反馈惊喜都回到既有 loop/memory 闭环，pet 只做"低优先级编排扩展"，不另起炉灶。

---

## 5. 错误处理

| 错误码 | 含义 |
|---|---|
| `PET_ALREADY_ACTIVE` | 会话已激活，重复激活被拒 |
| `PET_NOT_ACTIVE` | 会话未激活，唤醒/派发/恢复无效 |
| `PET_BACKOFF` | 会话处于异常退避态，暂不可唤醒 |
| `PET_YIELDING` | 主循环 busy，宠物让行（复用 orchestration `SUSPENDED`） |
| `PET_PREFERENCE_WRITE_FAILED` | 偏好写入 L2 facts 层失败 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/pet-mode-interface.md`
- 规格：`doc/openspec/specs/pet-mode/spec.md`
- 复用接口：`loop-interface.md`（`Loop.run` 同步薄壳）、`ui-interface.md`、`im-interface.md`、`cli-ops-interface.md`、`memory-interface.md`（`MemoryEntry.source`）、`orchestration-interface.md`（任务状态机 `SUSPENDED`）
- 对偶：`doc/02-modules/beast-mode.md`（前台重大任务）
