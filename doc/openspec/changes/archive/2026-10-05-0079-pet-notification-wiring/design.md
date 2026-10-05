# design — pet 通知三环接线（change 0079 / 账本 E16）

## 决策 1：生产者落在 `wake()` 收尾，判据复用 `report()` 的反馈周期

规格场景「异步通知」是「宠物**完成任务**发现可回报结果 → 生成通知」。宠物「完成任务」的单元
就是 `wake()`（`Loop.run()` 同步薄壳逐次执行，E17 裁决：不常驻、由宿主驱动）⇒ 生产者点只能是
`wake()` 收尾。

产出内容复用**既有** `report()`：其 docstring 即「达到反馈周期时向主人汇报后台进展，不阻塞主循环」，
内部判据 `wake_count % feedback_period == 0` 就是「可回报」的定义。故**不新造**消息文案与频度策略
——只是把既有产出**真的投出去**。

```python
def wake(self) -> LoopResult:
    ...
    self._wake_count += 1
    self._notify_owner()          # 新增：唤醒收尾（入队，不阻塞）
    return result

def _notify_owner(self) -> None:
    if self._notifier is None or not self._on_feedback_cycle():
        return
    self._notifier(self.report())
```

`_on_feedback_cycle()` 同时被 `report()` 复用（原先 `report()` 内联同一表达式）⇒ 单一判据真源。

**已否决**：
- **让 `report()` 自己发通知**（`report()` 由「纯格式化」变成「有副作用」）——破坏既有契约
  （接口文档 §1 逐字：`report() -> str`），且调用方无从选择是否投递。
- **每次唤醒都投递**（不判周期）——`feedback_period` 的语义就是「反馈节拍」，绕开它属改写策略；
  且会刷屏。
- **`surprise()` 同拍投递**——`surprise()` 是「**主动执行**并制造惊喜」的动作，不是报告；无偏好时
  仍返回「已帮你安排」通用文案，投出去等于**谎报已完成的事**。留作账本项。

## 决策 2：投递点 = 唤醒收尾（`notify` 入队 → `flush` 投递），由组合根收成单一可调用体

`PetSession` 注入面是 `notifier: Callable[[str], None]`（接口文档 §1 逐字，change 0053 起），
它**只拿到入队函数**，拿不到 `flush`。把 `flush` 也塞进 `PetSession` 有两条路，均被否决：

- **加第二个注入参数**（`flush_notifications=...`）：一个协作者拆成两个可调用体传参，注入面从
  3 处（`PetSession.__init__` / `restore` / `PetActivator`）各增一参 ⇒ 面变大、契约变、测试要跟。
- **改注入类型为 `AsyncNotifier` 对象 / `Notifier` Protocol**：改动既有契约与接口文档签名，
  且 `PetSession` 会持有「队列 + 通道」两个都不属于它的概念（它只需**产出**）。

**采用**：注入面**一字不动**，由**组合根**把「入队 + 投递」收成一个可调用体：

```python
pet_notifier = AsyncNotifier(channel=_pet_notification_sink)

def _pet_notify(message: str) -> None:
    """生产即投递：入队后即经宿主节拍 flush（唤醒收尾投递点，账本 E16）。"""
    pet_notifier.notify(message)
    pet_notifier.flush()
...
notifier=_pet_notify     # PetManager.factory / PetActivator 共用
```

语义与用户裁决的「唤醒收尾 `notify` 入队 ↓ `flush` 投递」逐步一致 —— 只是两步**在同一收尾点相邻执行**
（生产者唯一点在 `wake()` 末）。`AsyncNotifier` 的「notify 只入队、不阻塞」语义**原样保留**（宿主节拍
可换成批量投递）；「不阻塞主循环」亦成立（宠物唤醒是低优先步骤，主循环不被它阻塞）。

**已否决**：
- **`PetSession` 内直接 `channel(msg)`**（绕过队列）——绕过 `AsyncNotifier` 契约（spec R13 的
  「notify 仅入队」），且把投递节拍焊死在生产者里。
- **`Runtime` 暴露 `pet_notifier` 字段、由宿主 flush**——当前**无任何宿主驱动 `wake()`**
  （E17 裁决「宿主驱动」，但三个入口里 `_pet` 只激活、`ui serve` 不调用），故「宿主 flush」今日
  **不可达** ⇒ 规格仍未满足。留给将来常驻宿主时再议（记账本项）。
- **`Runtime` 数据类加字段**——其字段集被多测试断言，且本变更无需。

## 决策 3：缺省通道 = stderr 一行（主人可见的观测面），宿主可注入替换

`AsyncNotifier.channel: Callable[[str], None]` 的设计意图就是「真实通道由宿主注入」（模块 docstring）。
今日无宿主 ⇒ 缺省必须给一个**真的能到达主人**的 sink，否则规格仍不满足。取 **stderr 一行**：

```python
def _pet_notification_sink(message: str) -> None:
    """宠物通知缺省投递：写 stderr（主人可见的观测面，不污染 stdout 机读输出）。"""
    print(f"[pet] {message}", file=sys.stderr)
```

**已否决**：
- **走 `Tracer`（observability）**——`TraceEvent` 是 **trace 作用域的 span 遥测**（`trace_id` /
  `span_id` / `kind ∈ {model_io, tool_call, effect, metric}`，`end_trace` 统一导出）。宠物通知
  **无 trace 上下文**，硬造 `trace_id` 会污染遥测域并让 `replay()` 出现无来源事件。
- **走 `logging`**——全仓 `src/` **零 `logging` 用法**（既有约定是 entry 层 `print`；遥测走 `Tracer`）。
- **缺省 `channel=None`**——即现状（队列永不清、规格未满足）。
- **新增配置项 `pet.notify_channel`**——YAGNI；宿主替换是**代码级注入**（`build_runtime` 内的
  一行），不需要配置面。

## 规格与文档

**规格中性**（`skip_specs: true`，同 change `0070`/`0078`）：`pet-mode/spec.md` 既有三处明文
（Pet Notification 异步投递 / Pet Safety Bounds 通知主人 / Pet Session Runtime Wiring 注入通知器）
已覆盖本变更的**要求**；缺省 sink 与投递节拍是**实现机制**，记 ADR-0076。

文档同步：
- `doc/03-interfaces/pet-mode-interface.md`：§1 依赖注入注记（change 0053 段）补「通知器已接线
  （生产即投递 + 缺省 stderr sink）」；§5 表「反馈」行补投递点。
- `doc/02-modules/pet.md`（若列举通知环节）：补接线。
- `doc/04-testing/test-cases.md`：新增 TC-PET 通知投递两例。
- `doc/01-architecture/adr.md`：ADR-0076 + 变更追踪行。

## 转出（不在本变更内，记账本）

1. **安全越界通知无生产路径**：`SafetyBounds.check` 无消费方（`PetSession._safety` 只赋值），
   宠物工具调用不经安全边界 ⇒ 规格「越界即暂停并通知主人」需**安全强制执行路径**。
2. **`surprise()` / `MicrotaskRunner` 零调用方**：无触发策略，接线即新造行为。
3. **`IMGateway` 零生产装配**：im 规格「分平台接入」需真实平台 Provider（C 类真后端）；
   亦为 pet 通知的将来真通道。
4. **无宿主驱动 `wake()`**：E17 裁决「宿主驱动、不常驻」，但当前三入口无一调用 ⇒ 自治循环与
   通知在**生产**仅在宿主驱动时可达（本变更使其「一旦被驱动即投递」）。
