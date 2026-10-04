# 设计 — feature-flag-gating（E10）

## 决策

1. **门控点落在组合根，名单归组合根。** `GATABLE_MODULES` 定义在 `src/core/runtime.py`，
   不放进 `configuration`：configuration 属 `BASE_MODULES`，不知道能力模块的名字（分层红线的
   精神，只认字符串也不算「知道」，但以此换得名单与装配点同处一地、单一真源）。configuration
   只提供**极性纯净**的谓词 `is_disabled(module)`。
2. **新增 `is_disabled` 而不改 `is_enabled` 的语义。** `is_enabled` 是「显式开启查询」（缺省
   false），接口文档已记载、测试已锁定；pet 的二级启用开关正是这个极性。装配裁剪是新极性的
   新谓词：`features.get(module) is False`（缺省 **不关**）。两个谓词对应两种模块策略
   （缺省关的 opt-in 模块 vs 缺省开的白名单模块），在接口文档里并列说明。
3. **名单 = `pet` / `beast` / `evolution`。** 选标准是「装配期有真实副作用或真实资源占用」：
   pet（`PetManager` 构造即读注册表 `pets.json`）、beast（`register_innate_skills` 把 20 神通
   注册进全局技能库）、evolution（引擎 + worker + loop `cold_path` 闭包）。`mcp` 不入选
   （装配是惰性的，其门控随 §9 的 B4 CLI 接线一并落）；`im` 不入选（`IMGateway` 至今无处装配，
   门控会是无对象的形式主义）；`ui` 不入选（在 `entry` 构造，不属组合根）。
4. **pet 的两级开关分层，互不覆盖。** `features.pet`（**装配**，缺省开）与 `pet.enabled`
   （**启用**，缺省关，`ConfigSpec` 单一真源，`--pet-enabled` / `CORE_PET_ENABLED`）是两回事：
   前者决定 PetManager 建不建、Web UI 宠物入口接不接；后者决定宠物模式是否放行激活。
   副产品是修掉一处**既有不一致**：今天 `pet` CLI 认 `pet.enabled`，而 Web UI 的 `activate_pet`
   因组合根永远装配 pet 而**无条件可用** —— 门控落位后两者的准入判据一致（装配面为空则
   `UIAPILayer.activate_pet` 报「宠物激活器未接」）。
5. **`cold_path` 随 evolution 关闭而置 `None`**，不塞空 lambda：`DefaultLoop` 本就接受
   `cold_path=None`（:119），造一个空闭包等于把「模块未装配」伪装成「装配了但不做事」。
6. **入口拒绝统一 `0` + stderr。** 对齐既有 `pet.enabled` 未启用形态（`entry._pet:929`）：
   「请求的功能未启用」不是进程错误。六处入口（`pet` / `summon` / `recall` / `evolve` 四子命令）
   一律「说明 + 退出 0」，文案含模块名与开关名，便于脚本判读。
7. **规格中性之外的一手核实**：`Runtime` 的字段集被多份测试断言（`test_phase13.py` 以
   `SimpleNamespace` 造替身），故**只**把五个字段改可空、不改字段集与顺序；`Runtime` docstring
   的「所有依赖非空」改为「除可门控的三模块外非空」。

## 已知接受项

- 关闭 pet 而 `pet.enabled=true`：CLI 打出「pet 模块已关闭」并退出 0（不再走激活路径）——
  这正是「关闭即不初始化」。
- 关闭 evolution 后 `evolve` 四子命令不可用（含 `pending` / `confirm` 这类**只读/写队列**的
  子命令）：队列本身由 `PendingQueue(path=...)` 承载，engine 是它的持有者；不为只读命令开
  第二装配路径（YAGNI）。
- 关闭 beast 后 20 神通不在全局技能库中：**这正是规格 R5 想要的**（神通只应经 beast 域路由
  可见），主 Agent 的候选集不受影响（域作用域本来就过滤掉它们）。

## 遗留（不在本变更内，转账本后续行）

- `features` 段未知模块名无告警（与 E18 同族：名单在组合根 ⇒ configuration 无从判名）；
- `features` 值非布尔被 `bool()` 强转（`pet: "off"` ⇒ True）—— `_build_config:373` 既有语义；
- `mcp`（随 B4）/ `im`（无装配点）的门控。
