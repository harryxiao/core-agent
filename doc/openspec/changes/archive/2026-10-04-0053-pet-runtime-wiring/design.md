# Design — pet-runtime-wiring

## 决策 1：pet 经组合根装配，而非入口现造

**背景**：`entry._pet` 现造 `PetManager()`/`PetActivator()`，与 `Runtime` 无连接。

**决策**：pet 依赖（`Explorer`/`SafetyBounds`/`AsyncNotifier`/`PetManager`/`PetActivator`）
由 `build_runtime` 组装，`Runtime` 增 `pet_manager`/`pet_activator` 字段。

**理由**：`runtime.py` 是唯一组合根（`tests/test_architecture.py::test_runtime_is_sole_composition_root`），
pet 依赖里含 `loop`/`memory` —— 只有组合根持有它们。入口侧「装配 → 用其面」是既有范式
（`_memory maintain`、`evolve run`、`_build_ui`）。`pet` 属 `CAPABILITY_MODULES`，组合根 import 合法。

**否决**：入口自建（拿不到 runtime 的 `loop`/`memory`，症状 2/3 无法闭合）。

## 决策 2：注册表落盘用「快照 + 恢复工厂」

**背景**：`PetManager` 持有**活** `PetSession`（内含 loop/memory，不可序列化）。

**决策**：
- `PetSession.snapshot() -> dict`：会话 id / 状态 / 任务队列 / 偏好 / 唤醒计数 / 故障 / 让行位。
- `PetManager(path=None, *, factory=None)`：init 时读 `pets.json`，逐条经 `factory(record)`
  重建会话；`register/start/stop/remove` 后写盘。
- 组合根传 `factory=lambda rec: PetSession.restore(rec, loop=…, memory=…, …)`
  → **加载的记录恢复为带真依赖的活会话**；缺省 `factory` 用 `PetSession.restore(rec)`（裸会话）。

**理由**：保持 `PetManager.list() -> list[PetSession]` 契约不变（既有 `_print_pets`/测试依赖它），
同时让跨进程恢复的宠物**仍是完整会话**（可继续 `wake`/`stop`）。落盘路径沿用
`$CORE_STATE_DIR`（`_skill_state_path` 先例），单文件 JSON（快照态，同 `skills.json`）。

**否决**：落「元数据记录」并把 `list()` 返回类型改成记录 —— 破坏既有契约与 `_print_pets`；
`PetManager` 改持工厂而破坏「注册表」单一职责。

## 决策 3：依赖注入加法式，缺省行为不变

`PetActivator.__init__(manager=None, *, loop=None, memory=None, explorer=None, safety=None,
notifier=None, busy=None)`，`_activate` 把这些透传 `PetSession(...)`。缺省全 `None`
→ `PetSession` 走既有兜底（echo loop / `memory=None`），`tests/test_pet_core.py` 三入口用例行为不变。
`PetManager`/`PetSession` 既有签名与语义不动，仅**追加**可选面。

## 决策 4：WebUI 自然语言入口落在 `UIAPILayer`

`UIAPILayer` 增 `pet_activator` 注入 + `activate_pet(user_input) -> str`（返回 session_id），
`_build_ui` 注入。`/pet` 斜杠命令面板（候选来自 `list_tools`）属 UI 层面，不进内核。

## 非对称风险与接受项

- **接受**：快照仅捕获**注册表级**态；宠物**运行中**的 loop 内部上下文本就不跨进程（编排层本就如此）。
- **接受**：`AsyncNotifier` 无 channel → `flush()` 投递为后续行；本次仅完成注入（不阻塞主循环的通知入队已成立）。
- **接受**：不自建后台调度线程（pet 仍显式 `wake`），daemon 化属另一变更。
