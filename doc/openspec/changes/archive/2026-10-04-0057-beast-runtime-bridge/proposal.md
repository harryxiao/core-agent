# 神兽运行时桥接（beast-runtime-bridge）

## Why

`beast-mode` 规格 R4/R5 正文里**自己写着**「runtime 调用 deferred」——即规格承诺的
「独立 loop + 共享记忆命名空间 + 神通注册进全局技能库 + 专属路由」，在生产装配里**一条都没接**：

1. `BeastManager.summon` 造 `BeastSession(beast)`，**不注入** loop / memory →
   `session.loop` 退化成 `DefaultLoop()` 默认实例（echo planner），`remember()` 直接抛
   `BEAST_MEMORY_WRITE_FAILED`（「记忆后端未接」）。
2. `build_innate_skills` / `register_innate_skills` **零生产调用方**——20 枚神通从不进技能库。
3. `SkillRouter.match` 候选池是全局 `SkillLibrary`，**无域过滤**——一旦注册，专属神通
   会被**主 Agent** 路由到并灌进主 prompt（违反 R5「仅该兽可路由」）。
4. `entry._summon` / `_recall` 造裸 `BeastActivator()`（无 manager 注入），每次新起一份空装配。

**因此「只注册不路由」不是中性半成品**：它会把系统推入「违反自己规格」的状态。
本变更按用户 2026-10-04 裁决「A 全做・解除 deferred」四项一次闭合。

## What Changes

- **规格**：`beast-mode` MODIFIED R4「Independent Sub-Agent with Shared Capability」与
  R5「Innate Skills and Dedicated Routing」——删去「runtime 调用 deferred」，写明组合根装配义务
  与**路由期作用域强制**口径（`domain` 过滤而非调用方自觉）。
- **注册**：组合根构造 `BeastRegistry` → `register_innate_skills(skill_library, registry)`（20 枚）。
- **作用域路由**：`SkillRouter.match(task, *, domain=None, ...)` —— 三节 `beast.<域>.<技能>` 为
  专属技能，仅 `domain == "beast.<域>"` 时进候选；主 Agent（`domain=None`）看不到任何专属神通。
- **注入**：`BeastManager(registry=..., router=..., loop_factory=..., memory=...)`，`summon` 时
  以 `loop_factory(beast)` 造**按兽装配**的独立 loop（域内路由）+ 注入共享 `MemoryStore`；
  `Runtime` 增 `beast_manager` / `beast_activator`；`entry._summon`/`_recall` 走 `build_runtime`。

## Impact

- 影响规格：`beast-mode` R4 / R5（MODIFIED ×2）。
- 影响代码：`src/core/skills/router.py`、`src/core/beast/{manager,skills}.py`、`src/core/runtime.py`、
  `src/core/entry.py`。
- 不新增依赖、不改插件契约、不改 Skill/Session 数据模型。
- 行为变化仅在**生产装配**（`build_runtime`）与 CLI `summon`/`recall`；库层默认（不传参）行为不变。
