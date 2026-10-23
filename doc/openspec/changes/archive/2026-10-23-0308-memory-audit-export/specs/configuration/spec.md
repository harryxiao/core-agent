# Spec Delta — configuration（0308 记忆审计日志配置）

## ADDED Requirements

### Requirement: 记忆审计日志配置

系统 SHALL 将记忆治理审计日志的开关纳入 ConfigSpec 单一真源：`memory.audit_log`，
缺省 `true`。三面 SHALL 齐备：CLI flag `--memory-audit-log`、环境变量
`CORE_MEMORY_AUDIT_LOG`、config.yaml `memory.audit_log`。

组合根 SHALL 在 `audit_log_enabled()` 为真时构造
`MemoryAuditLog($CORE_STATE_DIR/memory.audit.jsonl)` 并注入 `MemoryStore`；为假时注入
`None`（不创建文件、不写事件）。

取值归一与 `memory.key_fact_extract` 同口径（原生布尔 / `true`·`false`·`yes`·`no`·
`on`·`off`·`1`·`0`，大小写不敏感）。`memory` 为非结构化段 ⇒ 集合外取值 SHALL 归一为
**开启**（笔误不得静默关闭审计）；未加载配置时访问器 SHALL 返回 `true`。

#### Scenario: 缺省开启并接线

- **GIVEN** 未配置 `memory.audit_log`
- **WHEN** 组合根构造 `MemoryStore`
- **THEN** 审计日志已接线，首次治理动作在 `$CORE_STATE_DIR/memory.audit.jsonl` 落一行

#### Scenario: 三面关闭

- **GIVEN** `memory.audit_log` 经 yaml / CLI flag / 环境变量任一设为 `false`
- **WHEN** 组合根构造 `MemoryStore`
- **THEN** `audit_log` 为 `None`；治理动作不产生审计文件

#### Scenario: 环境变量覆盖 yaml

- **GIVEN** yaml 为 `true`、环境变量为 `false`
- **WHEN** 读取 `audit_log_enabled()`
- **THEN** 返回 `false`

#### Scenario: 非法取值归一为开启

- **GIVEN** `memory.audit_log` 取 `disable` / `ong` / 空串
- **WHEN** 读取 `audit_log_enabled()`
- **THEN** 返回 `true`，不阻断启动
