# 0079 pet 通知三环接线（账本 E16）

## Why

账本 **E16**「`AsyncNotifier` 无 channel」，一手核实后**比记载严重 —— 通知链路三层全断**：

| 环 | 现状（一手核实） |
|---|---|
| 生产者 | `PetSession._notifier` **只赋值、全程零调用**（`grep -rn "_notifier" src/core/pet/` 仅见 `session.py:49` 构造行）；`report()`（「达到反馈周期时向主人汇报」）与 `surprise()` **零调用方**（含测试） |
| 通道 | 组合根 `runtime.py:653` `AsyncNotifier()` **不传 `channel`** ⇒ `flush()` 恒返回 0、队列永不清空 |
| 投递点 | `AsyncNotifier.flush()` 全仓 **零调用方** |

即 `pet-notify` 是**孤立模块**：单测 `AsyncNotifier(channel=delivered.append)` 自证类自身可用，
但生产的**生产者 / 通道 / 投递点**三处皆空 ⇒ 规格 `pet-mode/spec.md`「**Pet Notification**」
（「SHALL 支持宠物主动通知主人…通知**异步投递**、不阻塞主循环」+ 场景「异步通知」）**未满足**，
`doc/03-interfaces/pet-mode-interface.md` §5 表里「反馈 `report()`：达到周期向主人汇报」「惊喜
`surprise()`：结果反馈主人」两条契约亦**无投递**。

账本 E16 自述前置「IM 通道（`im`）为依赖」经核实**该前置不存在**：`IMGateway` 在 `src/` 内
**零生产装配**（仅自身模块 + 单测 + 配置 spec 映射 + 接口文档），im 规格「分平台接入」又要求
真实平台 Provider（Telegram/飞书/企业微信…）⇒ 属 C 类真后端，**今日接不了**（另立账本项）。

故本变更按用户裁决「**接生产三环 + 默认可替换通道**」落地：让**既有**三环真的连通，缺省通道
取主人可见的观测面（stderr），IM 真通道留作宿主注入替换（另立账本项）。

规格 `pet-mode/spec.md` 既有条款（Pet Notification「异步投递」、Pet Safety Bounds「越界即暂停并
通知主人」、Pet Session Runtime Wiring「…安全边界与**通知器**」注入）已明文要求 ⇒ 属
「**规格要求 X、实现没有**」型（同 E21/E22/E15）：**改代码向规格靠拢，规格不动**（`skip_specs`）。

## What Changes

- `src/core/pet/core/session.py`：`wake()` 收尾产出通知 —— 反馈周期命中（`wake_count %
  feedback_period == 0`）时 `self._notifier(self.report())`（仅入队，不阻塞）。抽出
  `_on_feedback_cycle()` 供 `report()` 与生产者共用（消除重复判据）。
- `src/core/runtime.py`：组合根给 `AsyncNotifier` 接**缺省通道**（stderr 一行，主人可见的观测面），
  **并**把「生产即投递」的宿主节拍收成一个可调用体（`notify` 入队 → `flush` 投递）注入
  `PetManager`/`PetActivator` —— 注入面签名不变（仍是 `Callable[[str], None]`），唤醒收尾即投递点。
- 测试：`tests/test_pet_core.py` 加**生产者**用例（周期命中投递 / 未命中静默 / 无 notifier 兜底不变）；
  `tests/test_pet_wiring.py` 加**组合根连通**用例（生产激活的会话持有可投递通道，调用即达 sink）。

## Non-goals

- **不**接 IM 真通道（`IMGateway` 零生产装配 + 需真实平台 Provider，属 C 类真后端）—— 另立账本项。
- **不**接安全越界通知：`SafetyBounds`/`Explorer` 虽注入 `PetSession` 但**零消费**（宠物工具调用
  未经安全边界），故「越界即暂停并通知主人」需要**安全强制执行路径**（另一项工作）—— 另立账本项。
- **不**动 `surprise()` / `MicrotaskRunner`（零调用方，无触发策略；接线会**新造**行为）—— 另立账本项。
- **不**加 daemon / 调度线程驱动 `wake()`（E17 已裁决：唤醒由宿主驱动、内核不常驻）。
- **不**加 spec delta：规格既有条款已覆盖，同 change `0070`/`0078` 判 `skip_specs`。

## 风险

- **既有用例零回归**：`grep -rn "notifier" tests/` 仅 `test_pet_notify.py` 直接构造 `AsyncNotifier`；
  无任何测试向 `PetSession`/`PetActivator` 传 `notifier=`，故新增生产者不影响既有断言。
- **缺省通道写 stderr**：仅在**反馈周期命中且宿主驱动 `wake()`** 时产出（`feedback_period` 缺省 5）
  ⇒ 不刷屏、不污染 stdout 机读输出（CLI 打印走 stdout）。
