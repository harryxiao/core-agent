# design — 功能开关三面接线与取值统一

## 决策

### ① 取值集合：接受常见别名，拒绝未知取值

| 归一结果 | 取值（大小写不敏感、忽略首尾空白） |
|---|---|
| 真 | 原生布尔 `true`、`true` / `yes` / `on` / `1` |
| 假 | 原生布尔 `false`、`false` / `no` / `off` / `0` |
| **非法** | 其余一切（`maybe`、空串、映射、`1.0` 等）⇒ **校验期拒绝并阻断启动** |

理由：`off` / `no` 是 YAML 1.1 的惯用写法、也是用户**无歧义**的意图表达，本仓解析器按 YAML 1.2
核心 schema 只认 `true/false` ⇒ 落成字符串 ⇒ `bool("off") is True` 把「显式关闭」当作开启。
与 B5（出站白名单）的差异：那里拒绝带 scheme / 端口的条目是因为它们**永不匹配**（语义错配）；
此处 `off` 的语义**明确无歧义** ⇒ 归一而非拒绝。

**已否决**：只收 yaml 原生布尔（把 `off` 判为错误）—— 与环境面 / 用户直觉不一致，且会让
`--feature beast=off` 与 `features.beast: off` 两个面行为不同；静默强转（现状）—— 缺陷本身。

### ② 归一位置：构建前（`_build_config`），不并入 `validate_schema`

`features` 是**结构化段**（不是 `extra` 里的原始取值），`_build_config` 一旦把它化为布尔，
原文即不可追溯 —— 故「非法取值」只有**构建前**才看得见。这与 `load()` 顶部 `validate_map_to`
（同为构建前 `raise ConfigurationError`）同属一条「构建前阻断」通道；`validate_schema` 继续负责
**取值留存于 `extra`** 的那些校验（密钥引用 / `permission.mode` / 约束阈值 / 出站白名单）。

**已否决**：把 `features` 挪进 `extra`（改变结构化段契约，波及 `is_enabled` / `is_disabled` /
`config show`）；把原文塞回 `AppConfig` 供 `validate_schema` 事后校验（为一个校验点污染数据模型）。

### ③ CLI 面：`_cli_overrides` 单独收集，不入 `ConfigSpec`

模块名是**开放集合**（`GATABLE_MODULES` 归组合根，配置层不认识模块名 —— ADR-0065 的分层决定），
故 `--feature` 不能像 `pet.enabled` 那样写成 `ConfigSpec`。收集点在 `_cli_overrides`：
它产出的是**覆盖层**，`_apply_cli` 按点分路径写入 ⇒ `cli["features.beast"] = "false"` 与
yaml / env 走**同一条**归一/校验路径。裸名（`--feature pet`）按 metavar `NAME[=BOOL]` 语义视为开。

语法非法（`--feature =false` / `--feature pet=`）在**解析点**拒绝（`非法 --feature 取值`）——
这是 flag 形状错误，与「取值不合法」是两回事；后者交由配置层单一真源判定。

### ④ env 面写入原文

`_apply_env` 原本就地 `value.lower() in ("true","1","yes")` 强转（`CORE_FEATURES_X=banana` ⇒
静默为假）。改为写入**原文**后，三面（yaml / env / CLI）在 `_normalize_features` **单点**归一，
「合法集合」只有一处定义。

## 影响面

| 面 | 处置 |
|---|---|
| 行为变化 | yaml `off` / `no` / `"false"` / `0` 由「静默为**开**」变为**关**（即用户本意）；`maybe` 之类由静默为开/关变为**阻断启动** |
| 既有写法 | 原生 `true` / `false` 与 env `...=true` 行为**逐位不变**（回归用例锁住） |
| 分层红线 | 不动：`configuration` 不 import `runtime`；`entry` 组装的 `features.*` 覆盖键经**覆盖层**进入 `manager` |
| 既有用例 | `tests/test_feature_gating.py`（18 例）/ `tests/test_configuration.py`（env `CORE_FEATURES_VOICE_OUTPUT=true`）全绿 |
