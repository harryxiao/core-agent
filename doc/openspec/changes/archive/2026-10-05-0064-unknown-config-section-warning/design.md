# 设计：unknown-config-section-warning（E18）

## 1. 缺陷判定：为什么是「仅告警」而不是「硬拒」或「静默」

三选一的取舍（用户裁决取 ①）：

| 方案 | 后果 | 判定 |
|---|---|---|
| ① **仅告警** | 启动不阻断、错误可见；段仍留在 `extra` | ✅ 采纳 |
| ② 硬拒（白名单） | **拒绝既有自定义段** —— 改变既有接受行为，`extra` 的契约就是「结构化段之外的一切」 | ✗ 破坏性 |
| ③ 维持静默 | 拼错段名无处暴露，用户被误导性报错引向错误方向（= E18 病灶本身） | ✗ |

① 的实质是**把「宽松接受」与「错误可见」解耦**：接受行为不变（不破坏），但错误不再隐形。

## 2. 白名单：为什么必须派生而不是另立清单

已知段 = **三个来源的并集**，全部来自既有单一真源：

```python
def _known_sections(self) -> set[str]:
    declared = {spec.map_to.split(".", 1)[0] for spec in self._specs if "." in spec.map_to}
    return set(_STRUCTURED_SECTIONS) | set(_KNOWN_EXTRA_SECTIONS) | declared
```

- `_STRUCTURED_SECTIONS`：`_build_config` 逐段解析的五个段 —— **解析器实际认识的段**；
- `declared`：`_CONFIG_SPECS` 的 `map_to` 前缀 —— 新增 `ConfigSpec` **自动进白名单**；
- `_KNOWN_EXTRA_SECTIONS`：寄居 `extra` 但**有运行时语义**的段（`permission`——本模块消费
  `permission.mode` 并做枚举校验），它是「已知」的，告警它会误导。

若改成手写一份段名清单，就是**第二真源**：`_CONFIG_SPECS` 增段时清单会漏改，于是新生效的段
反而被告警。派生法使「白名单 ⊆ 认识的东西」恒成立。

## 3. 告警的产生与发出分离

- **产生**：`validate_schema` 是**纯谓词**，返回 `ValidationResult(ok, errors, warnings)`。
  `warnings` 只是返回值里的一项 —— 校验函数**不产生副作用**，测试可直接断言
  `result.warnings`，不必捕获异常或打桩。
- **发出**：`load()` 在校验通过后 `warnings.warn(w, stacklevel=2)`。
  - 为何在 `load()` 而不在 `validate_schema`：`load()` 是**配置生效**的入口，告警属「生效时的提示」；
    且 CLI `config validate` 走的也是 `load()` ⇒ **一处发出，CLI 与库调用方都看得见**（零接线）。
  - `stacklevel=2`：让警告指向**调用方**（`load()` 的调用点），而非 manager 内部行 —— 对
    `pytest.warns` 与真实用户都更有用。
  - 为何用 stdlib `warnings` 而不接 `observability`：本模块在 `BASE_MODULES`，**不得**依赖能力模块；
    且 `warnings` 无需装配、默认对 stderr 可见 —— 一个「提示」不值得引入日志接线。

## 4. 口径边界：只到顶层段名

告警判据是 `set(config.extra) - known`，即**顶层段名**之差。

- `llmm:\n  model: typo` → `extra["llmm"]`，`llmm` ∉ known ⇒ **告警**；段仍保留在 `extra`。
- `llm:\n  endpont: x` → `llm` ∈ known ⇒ **不告警**（子键未知不判）。

理由：未知**段名**几乎总是拼写错误（用户想配 `llm` 却写成 `llmm`），这是本账本项的作用域；
未知**子键**可能是前向兼容的自定义扩展（如 `llm.extra_headers`），逐能力判定，需要各能力
自己的 schema。判到子键 = 要求「配置全量 schema 化」，超出本变更。

## 5. 副作用与回归面

- `ValidationResult` 加字段是**加法式**：`warnings` 有默认值，既有构造点（`ConfigurationError`
  路径等）不传即空列表；既有断言 `result.ok` / `result.errors` **逐字不变**。
- `extra` 契约不变（段不丢弃）⇒ **无任何既有消费者受影响**（唯一行为变化是**多一条 stderr 告警**）。
- 测试：`tests/test_configuration.py` 4 例（告警 + 已知段不告警 + 已知段内子键不告警 +
  `ValidationResult.warnings` 默认空）+ `tests/test_entry.py` 1 例（CLI `config validate` 退出码仍 0、
  打印「配置有效」且发出告警）。前者为**行为契约**，后者证明**生产接线**（CLI 路径上真能看见）。
