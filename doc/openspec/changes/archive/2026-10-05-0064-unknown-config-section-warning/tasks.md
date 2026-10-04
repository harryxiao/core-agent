# 任务：unknown-config-section-warning（E18）

## 1. 规格先行

- [x] 1.1 `configuration` spec「配置校验与生效」MODIFIED（增「未知配置段 SHALL 仅告警」）+ 新场景
      「未知配置段仅告警不阻断」→ `specs/configuration/spec.md`
- [x] 1.2 用户裁决落地：仅告警（WARN 不阻断），段不丢弃

## 2. 测试先行（红 → 绿）

- [x] 2.1 `tests/test_configuration.py`：未知段 `llmm` 告警且 `ok is True`、段留在 `extra`
- [x] 2.2 已知段（含 `permission`）无告警
- [x] 2.3 已知段内部子键未知**不**告警（口径只到顶层名）
- [x] 2.4 `ValidationResult.warnings` 默认空（加法式不破坏既有构造）
- [x] 2.5 `tests/test_entry.py`：CLI `config validate` 发告警 **且**退出码 0 / 打印「配置有效」
- [x] 2.6 确认红（`ValidationResult` 无 `warnings` → `AttributeError`），实现后转绿

## 3. 实现

- [x] 3.1 `models.py`：`ValidationResult.warnings: list[str] = field(default_factory=list[str])`
- [x] 3.2 `manager.py`：`_STRUCTURED_SECTIONS` / `_KNOWN_EXTRA_SECTIONS` + `_known_sections()`（派生）
- [x] 3.3 `manager.py`：`_unknown_section_warnings()` 产出 + `validate_schema` 返回 `warnings`
- [x] 3.4 `manager.py`：`load()` 发出 `warnings.warn(..., stacklevel=2)`（仅告警不阻断）

## 4. 文档

- [x] 4.1 `doc/03-interfaces/configuration-interface.md`：`ValidationResult` 形状 + §2.2 未知段口径
- [x] 4.2 `doc/02-modules/configuration.md` §5 校验表新行
- [x] 4.3 `doc/01-architecture/adr.md`：**ADR-0063**（仅告警 / 白名单派生 / 顶层段名口径 / warnings 发出点）
      + 变更追踪映射行

## 5. 验证与收尾

- [x] 5.1 四门全绿（ruff check / ruff format --check / pyright / pytest）
- [x] 5.2 `openspec validate 0064-unknown-config-section-warning` → 手动归档 →
      `openspec validate --all`
- [x] 5.3 账本 E18 行关闭 + §3 E18 段（关闭动作）+ §9 步骤 9
- [x] 5.4 `coding-plan/README.md` 同步
- [x] 5.5 提交 `feat(configuration): 未知配置段仅告警不阻断（change 0064）`
