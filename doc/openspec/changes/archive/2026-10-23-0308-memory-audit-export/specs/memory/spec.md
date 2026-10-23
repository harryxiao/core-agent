# Spec Delta — memory（0308 治理审计与导出）

## ADDED Requirements

### Requirement: 记忆治理审计日志

`MemoryStore` SHALL 接受可选构造参数 `audit_log`（`MemoryAuditLog | None`，缺省 `None`
⇒ 零文件、零行为变化）。接线后，存储 SHALL 在**动作成功之后**向 append-only JSONL 追加
治理事件（每行一个 JSON 对象，0600）：

- 成功写入（`_persist`）⇒ `op="write"`；
- 物理删除（`_delete_entry`）⇒ `op="delete"`；
- 自然衰减归档（`forget`）⇒ `op="forget"`，`reason="decay"`。

事件 SHALL 只含元数据：`ts / op / id / layer / kind / source / session_id / trace_id /
content_hash / reason / count / target / format`。事件 SHALL NOT 包含条目正文；除
`content_hash`（派生摘要，只截断）外的所有字符串字段 SHALL 先经 `redact_secrets` 并截断到
固定上界。

幂等重放（无落盘）、重要度闸门拒收（无落盘）、复用强化（`reuse_count` 自增）与层间迁移
SHALL NOT 产生审计事件。

审计追加失败 SHALL **不阻断**记忆操作（fail-open）：异常被吞掉并留一次进程内告警；记忆
写入 / 删除 / 遗忘的返回语义与未接线时逐字一致。

审计日志 SHALL 可由 `memory audit [--limit N]` 只读查看：按文件序返回尾部至多 N 行，
坏行跳过；文件缺失或为空时输出「（无审计记录）」并以 0 退出。

#### Scenario: 写入只记元数据

- **GIVEN** 接线了审计日志的存储
- **WHEN** 写入一条正文含密钥形态的条目
- **THEN** 日志新增一行 `op="write"`，含 id / layer / kind / source / content_hash；
  文件内不含条目正文或密钥明文

#### Scenario: 幂等重放不记审计

- **GIVEN** 同层同 id 同载荷条目已存在
- **WHEN** 再次写入同一条目（0306 快路径）
- **THEN** 不新增审计行、不落盘、不记效应

#### Scenario: 删除与遗忘可追溯

- **GIVEN** 一条待删除条目与一条衰减分低于阈值的 L2 episodic 条目
- **WHEN** 调用 `discard()` 与 `forget()`
- **THEN** 各新增一行 `delete` / `forget`；`forget` 行含 `reason="decay"` 与
  `content_hash`；条目仍在 L4 且带 `forgotten` 标签（墓碑未被另建一份）

#### Scenario: 审计失败不阻断记忆

- **GIVEN** 审计路径不可写（如指向目录）
- **WHEN** 写入一条条目
- **THEN** 写入成功返回 id；仅产生一次 `RuntimeWarning`

### Requirement: 记忆治理导出

CLI SHALL 提供 `memory export [--format jsonl|json] [--out PATH] --yes`：

- 缺少 `--yes` SHALL 拒绝导出（退出码 1，stderr 提示，stdout 不输出条目）；
- 快照 SHALL 覆盖后端全部条目（全层、含 superseded / forgotten），保持后端写序；
- 导出的每个字符串字段（含正文）SHALL 先 `redact_secrets`；`content_hash`（派生摘要，
  不含内容）除外，保留原值以便留档关联；
- `jsonl`（缺省）逐行 JSON；`json` 为缩进 JSON 数组；
- `--out PATH` SHALL 以 0600 写入文件；缺省写 stdout；
- 导出 SHALL NOT 修改条目、SHALL NOT 触发复用强化；
- 输出成功后 SHALL 追加一条 `op="export"` 审计事件（`count` / `target` / `format`；
  stdout 的 `target` 记 `-`）；审计未接线时该事件为 no-op。

#### Scenario: 缺确认不导出

- **GIVEN** 存储中有条目
- **WHEN** 执行 `memory export` 而未加 `--yes`
- **THEN** 退出码 1、stdout 为空、无文件写入

#### Scenario: 导出脱敏并留痕

- **GIVEN** 一条正文含密钥形态的条目
- **WHEN** 执行 `memory export --format jsonl --yes`
- **THEN** stdout 的 JSON 行不含密钥明文、正文已脱敏；审计日志新增
  `op="export"`、`count=1`、`target="-"`

#### Scenario: 文件导出权限

- **GIVEN** 指定 `--out` 且带 `--yes`
- **WHEN** 执行导出
- **THEN** 目标文件可被解析（json / jsonl）、权限为 0600
