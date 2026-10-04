# pet-runtime-wiring — 宠物子系统纳入组合根（E4）

## Why

账本 E4（`coding-plan/phase-19.md`）：**pet 子系统从未接入组合根** ——
`src/core/runtime.py` 零 pet 引用，`entry._pet` 每次调用**现造** `PetManager()`/`PetActivator()`
（`src/core/entry.py:818-819`）。四项同根症状：

1. **跨进程存活**：每次调用新建 `PetManager()`，进程退出即丢 → `pet gather` 后新进程 `pet list`
   看不见、`pet stop` 失效。
2. **依赖注入缺失**：`PetActivator._activate` 只传 `persona`，`PetSession(persona=persona)`
   拿到的是 **echo 的 `DefaultLoop()`** 且 `memory=None` → 偏好**落不到 L2**
   （违反 `pet-mode` 规格「Preference Tracking / 记录主人偏好」）。
3. **wake 无真触发**：即便唤醒，走的也是 echo loop（症状 2 的具体后果）。
4. **三入口不全**：`ui/api.py` 零 pet 引用 → WebUI 自然语言激活（`activate_from_nl`）未接
   （违反规格「Three-Entry Activation / WebUI 自然语言激活」）。

一手核实：`explore/`(Explorer) · `safety/`(SafetyBounds) · `notify/`(AsyncNotifier) 三层的具体实现
**均已存在且零三方依赖**，仅缺组合根构造与注入。前置 A3（存储选型）已由 change `0050` 关闭。

## What Changes

- **`build_runtime` 组装 pet 依赖**：构造一份 `Explorer`/`SafetyBounds`/`AsyncNotifier`，
  以 `path=$CORE_STATE_DIR/pets.json` 建 `PetManager`（落盘），
  并以 runtime 的 **`loop`/`memory`** + 上述三层建 `PetActivator`。
  `Runtime` 数据类增 `pet_manager`/`pet_activator` 两个字段（唯一构造点在 `runtime.py`）。
- **`PetManager` 落盘（跨进程存活）**：加法式 `path: Path | None = None` +
  `factory: Callable[[dict], PetSession] | None = None`；初始化时加载注册表快照，
  注册/启停后持久化。`factory` 让组合根把**加载的记录恢复为带真依赖的活会话**；
  裸 `PetManager()`（既有测试）行为不变。
- **`PetSession` 快照/恢复**：`snapshot() -> dict` 与 `restore(record, **deps) -> PetSession`
  （会话 id/状态/任务队列/偏好/唤醒计数/故障），供注册表落盘与恢复。
- **`PetActivator` 依赖注入**：构造函数增可选 `loop/memory/explorer/safety/notifier/busy`，
  `_activate` 透传给 `PetSession`（缺省全 `None` → 既有三入口测试行为不变）。
- **入口接线**：`entry._pet` 改用 runtime 的 `pet_manager`/`pet_activator`（对齐 `_memory`/`_evolve`
  的「装配 runtime → 用其面」范式）；`_build_ui` 注入 `pet_activator`；
  `UIAPILayer` 增 `activate_pet(user_input) -> str`（WebUI 自然语言入口）。
- spec delta：`pet-mode` —— MODIFIED `Multi-Pet Management`（注册表跨进程落盘）+ ADDED
  `Pet Session Runtime Wiring`（组合根注入真实依赖）。

## Non-Goals

- **不做后台 daemon**：宠物仍经显式 `wake()` 驱动，不自建调度线程（保持编排层语义；daemon 属另一变更）。
- **不接 IM 通知通道**：`AsyncNotifier` 无 `channel`，`flush()` 投递由宿主后续接（记后续行）。
- **不改 pet 四态枚举 / 让行语义**；**不接** `/pet` 斜杠命令的 UI 命令面板（候选来自 `list_tools`，属 UI 层面）。
- **不动** `PetSession` 生命周期方法签名；**不删**任何既有装配路径。

## Impact

- `src/core/pet/core/{session.py, manager.py, activator.py}`（快照/落盘/注入）
- `src/core/runtime.py`（组合根组装 + `Runtime` 两字段 + `_pet_state_path`）
- `src/core/entry.py`（`_pet` 改用 runtime；`_build_ui` 注入）
- `src/core/ui/api.py`（`activate_pet` 自然语言入口）
- spec：`doc/openspec/specs/pet-mode/spec.md`
- 文档：`doc/03-interfaces/pet-mode-interface.md`、`doc/02-modules/pet.md`、ADR-0056
- 账本：E4 关闭 + 后续行（IM 通知通道 flush / daemon 调度）
