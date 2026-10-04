# 未知配置段仅告警（unknown-config-section-warning）

## Why

账本 **E18**（change `0056` 裁决时由 E8 第 5 条转出）：`AppConfig.extra` 收纳「五个结构化段
（`llm` / `features` / `im` / `pet` / `judgment`）之外的一切」，于是**拼错的段名**（如 `llmm:`）
被**静默**吞进去——既不报「未知配置键」，也不提示拼错。用户看到的现象是「LLM 配置缺失」这类
**误导性**报错，与真实根因（段名拼错）相隔一层。

change `0056` 当时只裁定了「**不**收紧为白名单硬拒」（硬拒会拒绝既有自定义段，改变既有接受行为），
**未定**「那怎么让拼写错误可见」。本变更落定该形态。

**用户裁决（2026-10-05）：仅告警（WARN 不阻断）。**

## What Changes

- `src/core/configuration/models.py`：`ValidationResult` 增 `warnings: list[str]`（默认空）——
  `errors` 阻断生效、`warnings` 仅提示，两者语义分开。
- `src/core/configuration/manager.py`：
  - `validate_schema` 除 `errors` 外**产出**未知段告警（`_unknown_section_warnings`）；
  - 已知段白名单 `_known_sections()` = 五个结构化段 ∪ `ConfigSpec.map_to` 前缀 ∪ 有运行时语义的
    `extra` 已知段（`permission`）——**由单一真源派生**，不另立段名清单；
  - `load()` 在校验通过后 `warnings.warn(..., stacklevel=2)` **发出**告警（副作用不混进校验谓词）。
- `tests/test_configuration.py` + `tests/test_entry.py`：告警/不告警/不阻断/CLI 可见 四组用例。
- `doc/03-interfaces/configuration-interface.md`（§2.1 `ValidationResult` 形状 + 新 §2.2 口径）、
  `doc/02-modules/configuration.md` §5（校验表新行）。

## 规格 delta

`configuration` spec「配置校验与生效」**MODIFIED**：正文增「未知配置段 SHALL 仅告警」一段
（含已知段定义与「口径只到顶层段名」），并新增场景「未知配置段仅告警不阻断」。

## 明确不做

- **不硬拒**：白名单硬拒会拒绝既有自定义段，与 `extra` 的宽松契约冲突（change `0056` 已否）。
- **不静默**：完全静默则拼写错误无处暴露，正是 E18 的病灶本身。
- **不递归校验已知段内部子键**（`llmm:` 告警，`llm.endpont:` 不告警）：子键校验需要逐能力 schema，
  属各能力自己的义务；顶层段名正是「段名拼错」的**充分**作用域，再往下会越界成「配置全量 schema 化」。
- **不丢弃该段**：告警后仍留在 `extra`（既有行为不变）。
- **不引入日志依赖**：用 stdlib `warnings`，零接线、零新依赖。
