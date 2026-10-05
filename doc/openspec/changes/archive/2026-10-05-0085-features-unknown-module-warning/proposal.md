# 0085 — `features` 段未知模块名告警（账本 E20①）

## 为什么（账本 E20①）

`features` 是结构化段，子键 = **模块名**（`features.<模块>: false` 关闭某可选模块）。模块名集合
（`GATABLE_MODULES = ("pet", "beast", "evolution")`）是**组合根单一真源**，配置层不认识它。

今天的现实：`validate_schema` 只查**顶层段名**（规格 `configuration/spec.md`「配置校验与生效」
逐字写「告警口径 SHALL ONLY 作用于顶层段名，不递归校验已知段内部的未知子键」）。于是：

```yaml
features:
  peet: false   # 拼错（应为 pet）
```

`_normalize_features` 照样归一为 `{"peet": False}`；而 `is_disabled("pet")` 查的是 `"pet"`
（`features.get("pet") is False` ⇒ `None is False` ⇒ 假）⇒ **pet 照旧装配**。用户以为关了，
实际没关 —— **拼错的模块名静默 no-op**。对门控类开关（`pet`/`beast`/`evolution`）这是有实际风险的。

## 用户裁决

- **方案 ①：注入已知模块名（DI）**。`ConfigManager` 增注入面 `known_modules`，
  由**拥有集合的层**（组合根）传入 `GATABLE_MODULES`，配置层**代其校验** ——
  不改 ADR-0065「配置层不认识模块名」的归属（配置层仍不 import runtime、不硬编码模块名，
  只是**接收**一份集合，同既有 `specs=` 注入惯用法）。
- **仅告警，不阻断**：与 E18（未知配置段仅告警）同口径；模块名本为**开放集合**，
  开放集合里合法的新键最多吃一条可忽略的告警，绝不误阻断启动。
- **缺省不校验**：未注入已知集合（如裸 `ConfigManager(...)`）⇒ **不告警**（向后兼容，
  既有测试与 `features: voice_output: false` 之类自定义键不受影响）。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/configuration/manager.py` | `ConfigManager.__init__` 增 `known_modules: Iterable[str] \| None = None`（缺省 `None`=不校验）；新 `_unknown_feature_warnings(config)`：`features` 子键 ∉ 已知集合时产出告警（含模块名清单与「拼错将静默不生效」提示）；`validate_schema` 的 `warnings` 并入 |
| `src/core/entry.py` | `from core.runtime import GATABLE_MODULES, ...`；新增 `_config_manager(args, *, yaml_path=None)` helper（统一注入 `known_modules=GATABLE_MODULES`）替换全部构造点 ⇒ **单一注入点、不散落** |
| `doc/openspec/specs/configuration/spec.md` | MODIFIED「配置校验与生效」：顶层段名口径**加 `features` 例外**（按组合根维护的已知模块名校验、未知仅告警）+ 新场景 |
| `doc/03-interfaces/configuration-interface.md` | §2 构造签名补 `known_modules`；§2.3 补「`features` 子键例外」 |
| `doc/01-architecture/adr.md` | ADR-0080（注入归属 + 仅告警 + 缺省不校验）+ 映射表行 |
| `doc/04-testing/test-cases.md` | TC-CONF-0x（feature 子键告警） |

## 明确不做

- **不在配置层硬编码模块名**（会与 `GATABLE_MODULES` 成两处真源，且逆转 E10/ADR-0065 归属）。
- **不改「五个结构化段」字面枚举**（`features` 本就是其中之一，本次只在段**内**加子键口径）。
- **不硬拒未知模块名**：模块名是开放集合（`is_enabled` 供缺省关模块自查二级开关），
  硬拒会拒绝合法的新开关；仅告警足以暴露拼写。
- **不校验其它已知段的未知子键**（`llm.typo_key` 等）：那是各能力 schema 义务，非本项。
