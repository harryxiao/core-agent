# Change 0250 — 宠物人格固定与故障韧性

## 为什么

宠物专项复盘（change `0250` 前置只读盘点）确认三处**生产可达**的缺陷，均与既有规格承诺不符：

1. **人格跨进程丢失**：激活时注入的人格只活在当前进程的会话对象里。`snapshot()` 不含人格，
   组合根的恢复工厂（`runtime.py:1426`）也没传 `persona=` ⇒ 任何从注册表恢复的会话都是**无
   人格裸任务**。规格「Pet Persona and Prompt」「Multi-Pet Management（独立人格）」在新进程
   恢复后不成立。
2. **唤醒进度与队列跨进程丢失**：注册表只在 `register` / `start` / `stop` / `remove` 落盘。
   `wake`（消费任务、`wake_count++`）、`assign`、`sleep` 全部内存态 ⇒ 新进程看到的是**旧快照**：
   已消费任务复活（重放）、已派发任务丢失、唤醒计数归零。
3. **唤醒异常无退避、无恢复途径**：`PetSession.wake()` 直接 `asyncio.run(...)`，异常裸抛；
   `backoff()` 存在但**无任何生产调用方**，`BACKOFF` 一旦进入也没有出口。规格「异常退避」
   （标记故障态、隔离）在唤醒路径上未落地；驱动侧 `FAILED` 记录了失败，但任务已出队 ⇒
   失败任务**静默丢失**且宠物永久停在故障语义之外。

## 改什么

- **人格固定（persona pinning）**：`PetSession.snapshot()` 增加 `persona` 字段
  （`name/species/persona_text/traits/preferences`，无人格时为 `None`）；
  `PetSession.restore(..., persona_factory=None)` 按「显式人格 > 快照 + 工厂 > 无」解析；
  新增 `persona_from_record()` 反序列化；组合根恢复工厂传 `persona_factory=persona_from_record`。
- **注册表持久化边界**：新增 `PetManager.persist()`（公开、幂等）；`PetWakeDriver` 每次 tick
  之后由运行命令落盘；`PetControl.sleep/wake/assign` 在变更后落盘（`stop` 已落盘）。
- **唤醒故障韧性**：`wake()` 捕获 `Exception`（不捕获 `CancelledError`/`KeyboardInterrupt`）⇒
  `backoff(exc)` 置 `BACKOFF` + 故障原因后**重新抛出**（驱动按 `FAILED` 记录、不中断其余宠物）；
  新增 `PetSession.recover()`（`BACKOFF → ACTIVE`、清故障；其余态抛 `PET_NOT_ACTIVE`），
  控制面 `wake` 对 `BACKOFF` 会话走 `recover()`，其余仍走 `resume()`。

## 影响面

- 规格：`pet-mode` 四条 Requirement **MODIFIED**（新增行为段 + 5 个 Scenario，既有 Scenario 逐字保留）。
- 代码：`src/core/pet/core/{session,manager,control}.py`、`src/core/pet/library/persona.py`、
  `src/core/runtime.py`、`src/core/entry.py`。
- 测试：新增 `tests/test_pet_resilience.py`；既有 `tests/test_pet_*.py` 回归。
- 缺省行为：无人格、无注册表路径（纯内存）的调用方逐字不变（`persona=None`、`persist()` 无操作）。

## 不做

- 不做跨进程**驱动**（控制面仍只作用本进程 live 会话，规格明文「有意不做跨进程」）。
- 不做自动重放失败任务（唤醒失败的任务**不**回队；重派由主人/控制面决定，避免静默重试烧 token）。
- 不新增状态枚举（`BACKOFF` 既有）、不新增配置键。
