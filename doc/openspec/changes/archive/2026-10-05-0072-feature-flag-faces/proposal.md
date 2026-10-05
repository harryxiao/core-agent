# 功能开关三面接线与取值统一（feature-flag-faces）

## Why

账本 **E20②**（`features` 取值被 `bool()` 静默强转）与 **E23**（`--feature` CLI 面零消费），
均为 change `0067`（E10 功能开关门控，ADR-0065）的伴生发现。

规格「功能开关（feature flag）」明文列出**三条输入通道**（yaml / env `CORE_FEATURE_*` /
CLI `--feature <模块>=false`），且 `doc/03-interfaces/configuration-interface.md` §2.2 与
`ADR-0065` 都写「三条输入通道早已齐备」。实测**两处不符**：

1. **CLI 面静默无效**（一手核实）：`--feature pet=false` 只解析进 `args.feature`，
   而 `_cli_overrides` 仅收集 `ConfigSpec` 声明键 ⇒ 该值**无任何读者**（`args.feature` 全仓零消费），
   flag 形同虚设 —— 且**不报错**，用户以为关闭了模块、实际照常装配。
2. **取值静默强转**：yaml 子集解析器只认 `true/false/null/~`（`_BOOL_NULL`），故
   `features.beast: off`（YAML 1.1 的常见写法）落地为**字符串** `"off"` ⇒ `bool("off") is True`
   ⇒ **显式关闭被当成开启**；加引号的 `"false"`、`no` 同理。`config set features.x=maybe`
   也走同一条强转。

两者都是「**配了却没按意图生效**」型缺陷（与 E15/B5 的「不静默兜底」一脉）。

## What Changes

- `src/core/configuration/manager.py`
  - 新增 `_normalize_features(raw) -> dict[str, bool]`（**单一归一/校验点**）：接受原生布尔与
    `true/false`、`yes/no`、`on/off`、`1/0`（大小写不敏感、忽略首尾空白），其余取值
    **校验期拒绝并阻断启动**（含键名与合法取值）。
  - `_apply_env`：env 面写入**原文**（不再就地 `value.lower() in (...)` 强转），交由统一归一
    —— 于是 `CORE_FEATURES_BEAST=banana` 由静默为假变为**阻断启动**。
  - `_build_config` / `_merge_patch`（`apply_change` 路径）改用同一归一函数。
  - **归一位置在构建前**（`_build_config`）：`features` 是结构化段，取值一旦化为布尔原文即不可
    追溯 —— 与 `load()` 顶部 `validate_map_to` 同属「构建前阻断」通道。
- `src/core/entry.py`
  - `_cli_overrides` 收集 `--feature NAME[=BOOL]` → `cli["features.<模块>"]`（模块名是**开放集合**，
    门控名单归组合根，故不入 `ConfigSpec`，ADR-0065）；裸名视为开。
  - 新增 `_parse_feature_flag(item)`：语法非法（缺名 / 缺值）当场拒绝（`非法 --feature 取值`）；
    取值本身交由配置层统一校验（单一真源）。
- `tests/test_feature_flag_faces.py`（新，23 例）：CLI 面接线（解析 / 优先级 / 语法拒绝 /
  **组合根端到端**：`--feature beast=false` ⇒ beast 不装配）、常见假值写法归一为关闭、
  真值写法、原生布尔回归、env 面归一、四面（yaml/env/CLI/yaml 空值）非法取值阻断、
  `apply_change` 同口径校验。
- 文档：`doc/03-interfaces/configuration-interface.md` §2.2（三面与取值口径）、
  `doc/00-product/user-guide.md`（**顺带订正**「缺省关闭」陈旧措辞 —— change `0067` 订正规格时漏改；补三面取值口径）、
  `doc/02-modules/configuration.md` §3.3、`doc/01-architecture/adr.md`（ADR-0069 + 映射表行）、
  `doc/04-testing/test-cases.md`（TC-CONF-06/07/08）。

## 规格 delta

`configuration` spec「功能开关（feature flag）」**MODIFIED**：正文补「三条输入通道 SHALL 全部生效」
「取值 SHALL 三面同口径（列出合法集合）」「其余取值 SHALL 在校验期拒绝并阻断启动，SHALL NOT 静默强转」
「CLI 面 SHALL 参与优先级链、裸名视为开」；新增三个场景（CLI 面覆盖 yaml 与环境 / 常见假值写法归一为
关闭 / 非法取值校验期拒绝）。

## 明确不在本变更内（仍记账）

- **E20①**（`features` 未知模块名无告警）：规格「配置校验与生效」明文写「告警口径 SHALL ONLY 作用于
  **顶层段名**，不递归校验已知段内部的未知子键」—— 补「段内未知模块名告警」须**先改规格**，
  属需裁决项，本次不动。
- **E24**（新报）：env 前缀 `CORE_FEATURES_`（复数）与规格/文档的 `CORE_FEATURE_<模块>`（单数）
  不符 —— 改 env 变量名是**对外可观测**的破坏性重命名，单独立项裁决；本次保留既有前缀。
- 未知名是否应「拼接纠错提示」（如 `--feature pett=false` 提示 `pet`）：无需求，YAGNI。
