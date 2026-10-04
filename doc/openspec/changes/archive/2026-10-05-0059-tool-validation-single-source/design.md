# 设计：tool-validation-single-source（E14）

## 决策 1：方向是 `tools → constraints`（一手核验，非拍脑袋）

`constraints` 是**校验口径的规格归属**（constraints spec「输入输出校验」已把「工具调用前校验输入 schema」
写成自己的义务），故真源留 `Validator`，由**使用方** import。核验：

- `tests/test_architecture.py` `BASE_MODULES = {plugin_registry, configuration, observability, core_profile}`
  —— **不含 `tools`/`constraints`**（两者同属 `CAPABILITY_MODULES`），故 phase0「底座不反依赖能力层」不适用；
- `test_phase1_capability_no_reverse_dependency` 禁集只有 `tools → {memory, llm_provider}`；
- `test_phase2_middleware_no_reverse_dependency` 禁集只有 `constraints → {loop, skills, orchestration}`；
- `grep` 核实 `constraints` 全包只 import stdlib + `core.plugin_registry` + 同包模块 → **无环**。

与 change `0052` 的 `loop/constraints_adapter.py`（`loop → constraints`）同型：**横切能力被使用方 import**。
反方向（`constraints → tools`）会污染横切层对 L1 的依赖，否决。

## 决策 2：复用既有公开 `Validator.validate_input`，不新增 API

不新造 `validate_args()` 之类模块级函数（YAGNI）：`validate_input(tool, args, schema) -> list[str]`
已是公开方法，`Validator` 是 `Protocol` 结构实现**无构造状态**，`Validator()` 即时构造成本可忽略。
provider 侧保留 `_validate_args` 方法壳作**适配器**（`list[str]` → `ToolError`），调用方与签名不变。

## 决策 3：行为中性 —— 消息与早返回语义逐字保留

| 情形 | 现状（provider 内联） | 改后（委托 + `errors[0]`） |
|---|---|---|
| 缺参 | 早返回 `缺少必需参数: {missing}` | `validate_input` 把缺参**列首位** → `errors[0]` 同句 |
| 错型 | 早返回首条 `参数 {key} 类型不符，期望 {expected}` | 同上，`properties` 遍历序一致 → 同句 |
| 通过 | `None` | `errors == []` → `None` |

差别仅在于：现在 provider 遇错型**立即返回**，`validate_input` **收齐全部**再返回——但 provider 只取
`errors[0]`，对外消息**逐字相同**。（不把全量错误列表外泄：`ToolError` 单错误契约不变。）

## 决策 4：防复发靠测试，而非注释

新增两类守护（`tests/test_tool_use.py`）：

1. **结构（红→绿的那条）**：`core.tools.provider` **不再**有 `_matches_type` 属性
   （副本被删，`core.constraints.validator._matches_type` 为唯一实现）；
2. **行为等价**：缺参 / 错型两类非法调用，经 `ToolProvider`（`ainvoke`）与经
   `Validator.validate_input` 得到的拒绝口径一致（同错误消息）。

## 决策 5：规格只改一处

`constraints` 侧写口径（它已声明该义务）；`tool-use` spec 的「参数校验」是**行为要求**，
本变更行为中性 → 不写 delta（同一句话写两遍正是要消灭的形态）。
