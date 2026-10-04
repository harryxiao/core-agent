# 功能开关运行时门控（feature-flag-gating）

## Why

账本 **E10**（`coding-plan/phase-0.md:32` 未勾验收框 → `phase-19.md` §3）。
规格 `configuration/spec.md`「功能开关（feature flag）」**逐字要求**：

> 系统 SHALL 支持模块级 feature flag：关闭的模块不加载、不初始化，实现功能裁剪。

三条输入通道**早已齐备**（yaml `features:` 段、env `CORE_FEATURE_*`、CLI `--feature NAME[=BOOL]`），
但**没有一个消费者**：`ConfigManager.is_enabled` 在生产**零调用方**（只有测试与接口文档），
`build_runtime` **无条件**构造全部模块 —— pet 注册表照读、20 神通照注册、进化 worker 照建。
规格要求的「关闭即不初始化」在实现里没有落点。

## What Changes

**用户裁决（2026-10-05）：白名单内的可选模块缺省开**（兼容现状：未声明即装配），
只有显式 `features.<模块>: false` 才不装配。

- `src/core/configuration/manager.py`：新增 `is_disabled(module)` —— 唯一判据
  `features.get(module) is False`（缺省 **不关**）；**保留** `is_enabled`（显式开启查询，
  缺省 false，供缺省关的模块自查）。
- `src/core/runtime.py`：
  - 组合根声明门控名单单一真源 `GATABLE_MODULES = ("pet", "beast", "evolution")`；
  - 三处装配块按名单裁剪：`pet`（`PetManager`/`PetActivator` 不构造 ⇒ **不读** state 目录下
    `pets.json`）、`beast`（`BeastRegistry` 不建、`register_innate_skills` **不注册** 20 神通）、
    `evolution`（`EvolutionEngine`/`EvolutionWorker` 不建，loop 的 `cold_path` 随之置 `None`）；
  - `Runtime` 的五个对应字段（`pet_manager` / `pet_activator` / `beast_manager` /
    `beast_activator` / `evolution`）改可空，docstring 的「所有依赖非空」订正为该五项的例外说明。
- `src/core/entry.py`：`pet` / `summon` / `recall` / `evolve run|pending|confirm|reject`
  六个入口对「模块已关闭」统一拒绝（stderr 说明 + 退出码 0，对齐既有 `pet.enabled`
  未启用形态）。
- `tests/test_feature_gating.py`（新）：缺省装配 / 显式 false 不装配 / 显式 true 等价缺省 /
  beast 关闭 ⇒ 神通**未注册** / pet 关闭 ⇒ 损坏的 `pets.json` 不被读（装配仍成功）/
  evolution 关闭 ⇒ `cold_path is None` / 核心面不受影响 / CLI 六入口拒绝。
- 文档：`doc/03-interfaces/configuration-interface.md`（两谓词口径）、
  `doc/02-modules/configuration.md`、`doc/02-modules/runtime.md`（装配裁剪表）、
  `doc/01-architecture/adr.md`（ADR-0065 + 映射表行）、`doc/04-testing/test-cases.md`（用例号）。

## 规格 delta

`configuration` spec「功能开关（feature flag）」**MODIFIED**：正文增「只管**模块装配**、
不改模块二级启用开关」「白名单内**缺省开**、显式 `false` 才不装配」「名单由组合根单一真源维护」
三句，并新增四个场景（缺省装配 / 装配面为空 / 不改二级开关 / 核心面不受影响）。

## 明确不在本变更内（转账本后续行）

- `features` 段**未知模块名**无告警（与 E18 同族；名单在组合根，configuration 不知道名字）；
- `features` 值非布尔（如 `pet: "off"` 字符串）被 `bool()` 强转 ⇒ 静默开启（`_build_config`
  既有转换语义，本变更不动）；
- `mcp` / `im` 的门控（MCP 随 §9 的 B4 CLI 接线，IM 通道尚未装配）。

## 影响面

`features` 段**当前无使用者**（缺省即装配 = 与今天逐位一致）⇒ 既有行为零变化：
`test_pet_wiring` / `test_beast_wiring` / `test_phase14` 对非空字段的断言全部照旧成立。
