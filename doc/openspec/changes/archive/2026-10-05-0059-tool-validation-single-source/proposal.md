# 校验口径单一真源（tool-validation-single-source）

## Why

账本 E14：同一套「schema / 类型 / 必填」校验口径在仓里**有两份实现**——

- `src/core/tools/provider.py:35 _matches_type` 与
  `src/core/constraints/validator.py:19 _matches_type` **逐字节相同**（`noqa: PLR0911` 都一样）；
- `ToolProvider._validate_args`（`provider.py:172`）与 `Validator.validate_input`
  （`validator.py:52`）**语义逐行等价**：同一 `required` 缺参早返回、同一 `properties` 遍历、
  同一两条错误消息模板。

这份重复是 E1 走查的直接残留：E1 订正了「校验空转」的旧说法——**校验生产实由工具层承担**，
constraints 的 `Validator` 只是**同一口径的第二份实现**（且其 `before` 从未接进 loop 中间件链，
见 change `0052` ADR-0055「有意未接」）。两份实现谁都不是「假的」，但**两处真源**意味着
任何一侧单独修补（新增 JSON Schema 类型、改错误口径）都会让「工具层拒绝」与「校验中间件拒绝」
**静默分叉**。

## What Changes

- **规格**：`constraints` MODIFIED「输入输出校验」——把「调用前 schema 校验」这一既有义务写明
  **口径单一真源为 `Validator`**，工具层**委托**之、不得另实现副本；新增场景
  「工具层与校验中间件口径一致」。
- **实现**：`ToolProvider._validate_args` 改为委托 `Validator.validate_input`，删除
  `provider.py` 内的 `_matches_type` 副本（`validator.py` 的那份成为唯一实现）。
  **行为中性**：拒绝码（`INVALID_ARGS`）与两条错误消息**逐字不变**。
- **文档**：`constraints-interface.md` / `tool-use-interface.md` 标注委托关系；
  `02-modules/{constraints,tool-use}.md` 同步；ADR-0062。

## 依赖方向（一手核验）

`tools → constraints` **合法**：`tests/test_architecture.py` 的
`BASE_MODULES`（`plugin_registry`/`configuration`/`observability`/`core_profile`）**不含 `tools`**；
`test_phase1_capability_no_reverse_dependency` 只禁 `tools → {memory, llm_provider}`；
`test_phase2_middleware_no_reverse_dependency` 只禁 `constraints → {loop, skills, orchestration}`。
且 `constraints` 全包**不 import `tools`**（无环）。与 change `0052` 的 `loop → constraints`（适配层落 loop 侧）
**同型**：由使用方 import 横切能力。

## 明确不做

- **不改 `tool-use` 规格**：其「参数校验」要求的是**行为**（缺参/错型直接拒绝），行为不变，规格中性；
  口径归属只在 `constraints` 侧记一次（避免同一句跨规格写两遍，正是本变更要消灭的形态）。
- **不动 `Validator.parse_output`**：planner 自解析、零生产调用方属 **E13**，另记。
- **不把 `Validator` 接进 loop 中间件链**：change `0052` 已裁决「有意未接」（校验已由工具层承担）。
- **不重构 `EffectTracker` 等相邻代码**（CLAUDE.md §3 外科手术式改动）。
