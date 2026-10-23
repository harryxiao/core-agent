# Spec Delta — memory（0312 冲突裁决的可见性与计数：SDD §5.5 可落地子集）

## MODIFIED Requirements

### Requirement: 关键事实的跨压实合并

跨压实批次重复抽取同一实体时，关键事实 SHALL 按实体 slug 维护**版本链**：
**取值未变** ⇒ 在活跃版本上**就地刷新**溯源（`trace_id` / `tags` 随本次压实刷新）；
**取值变化** ⇒ SHALL **新增版本条目**（`id = f"keyfact.{slug}.v{version}"`、`version` 递增、
`parent_id` 指向旧版），旧版 SHALL 置 `status="superseded"` 且 `superseded_by` 指向新版，
SHALL NOT 原地覆盖。任一版本条目的**首次出现时间戳**（`ts`）SHALL 在后续同版本就地刷新时保留；
新版本获得自己的写入时间戳（旧版时间戳不随之改写）。缺省检索 SHALL 只见 `status="active"`
的链头（旧版本经 `audit()` 追溯）；取代动作 SHALL 记可撤销效应并随同一
`compaction.<session_id>` trace 回滚（回滚新版 ⇒ 旧版恢复 active）。同批归并语义
（同批同 slug 只留首条）SHALL 保持不变。

一次**取值变化**即一次冲突裁决：裁决规则 SHALL 固定为「新证据 > 旧证据」（SDD §5.5 第 3 级，
本仓无 `trust` / `confidence` / 显式更正信号，其余规则不可判定）。裁决 SHALL 产生可查询的
留痕（审计事件、指标与 `memory conflicts`，见「冲突可见性」）；SHALL NOT 改写该要求的版本链
与时间戳语义。

#### Scenario: 跨压实同实体合并不新增条目

- **GIVEN** 两个压实批次抽取到同一实体、**相同取值**
- **WHEN** 第二批压实落库
- **THEN** 仍只有一条 `keyfact.<slug>` 条目（版本不变），`trace_id` / `tags` 刷新为第二批溯源

#### Scenario: 跨压实取值变化新增版本

- **GIVEN** 某实体的关键事实已在第一批压实落库（`version=1`）
- **WHEN** 第二批压实抽到**不同取值**
- **THEN** 新增 `keyfact.<slug>.v2`；首版 `status="superseded"`、`superseded_by` 指向 v2；
  **AND** 缺省检索只返回 v2，`audit()` 两版俱在

#### Scenario: 跨压实更新保留首见时间戳

- **GIVEN** 某实体的关键事实已在第一批压实落库
- **WHEN** 第二批压实抽到**相同取值**并就地刷新
- **THEN** 条目 `ts` 仍等于首次落库时间，未被重置为第二批写入时间

#### Scenario: 版本链可回滚

- **GIVEN** 第二批压实产生了 `keyfact.<slug>.v2` 并取代了首版
- **WHEN** 回滚第二批压实的 `compaction.<session_id>` trace
- **THEN** v2 被删除、首版恢复 `status="active"`（旧值重新可召回）

#### Scenario: 取值变化留下裁决痕

- **GIVEN** 某实体的关键事实已存在且版本链处于 active
- **WHEN** 新一批压实抽到**不同取值**
- **THEN** 除版本链变化外，指标 `memory.conflicts` 自增 1，且审计日志新增一行
  `op="conflict"`（`id` 为旧版、`target` 为新版、`reason="newer_wins"`）

### Requirement: 记忆治理审计日志

`MemoryStore` SHALL 接受可选构造参数 `audit_log`（`MemoryAuditLog | None`，缺省 `None`
⇒ 零文件、零行为变化）。接线后，存储 SHALL 在**动作成功之后**向 append-only JSONL 追加
治理事件（每行一个 JSON 对象，0600）：

- 成功写入（`_persist`）⇒ `op="write"`；
- 物理删除（`_delete_entry`）⇒ `op="delete"`；
- 自然衰减归档（`forget`）⇒ `op="forget"`，`reason="decay"`；
- 关键事实取值变化的取代裁决（`_supersede`）⇒ `op="conflict"`，`reason="newer_wins"`，
  `id` 为旧版、`target` 为新版 id（change 0312）。

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

#### Scenario: 取代裁决留审计痕

- **GIVEN** 接线了审计日志的存储，某实体的关键事实已存在
- **WHEN** 同一实体以**不同取值**再次落库
- **THEN** 新增一行 `op="conflict"`：`id` 为旧版 id、`target` 为新版 id、
  `reason="newer_wins"`；行内不含取值明文

### Requirement: 记忆运行指标快照

`MemoryStore` SHALL 提供 `metrics_snapshot() -> dict[str, float]`，返回**存储实例作用域**的
累计指标（生产运行时一个进程一个实例；不落盘、不跨实例共享；键名与 SDD §11.1 对齐）：

- `memory.writes.<kind>`：成功落库的写入数，按条目 `kind` 分组（`kind` 规范化：小写化、
  非 `[a-z0-9_]` 替换为 `_`、空值记为 `unknown`）；
- `memory.writes.deduped`：幂等重放快路径命中数；
- `memory.writes.rejected`：重要度闸门拒收数；
- `memory.recall.calls` / `memory.recall.candidates` / `memory.recall.injected` /
  `memory.recall.injected_tokens` / `memory.recall.excluded_by_budget` /
  `memory.recall.excluded_by_diversity`；
- `memory.consolidation.runs` / `memory.consolidation.failures` /
  `memory.consolidation.elapsed_ms`；
- `memory.conflicts`：关键事实取值变化的取代裁决次数（change 0312）。

固定键 SHALL 在快照中**始终存在**（未发生时值为 0）；`memory.writes.<kind>` 只在对应 kind
发生写入后出现。快照 SHALL 为零 I/O、零写回、零效应，SHALL NOT 包含条目正文、查询文本、
session / trace 标识。实例销毁后计数 SHALL 消失（SHALL NOT 宣称跨实例或跨进程持久）。

`read()` 委托 `recall()` SHALL 计入 recall 指标；存储内部为巩固决策打分等发起的检索
SHALL NOT 计入（避免虚增注入统计）。`consolidation.runs` SHALL 只在压实**实际执行**时计数
（开关关闭 / 并发跳过不计）；执行抛错 SHALL 计入 `failures` 后照常向上抛出；`elapsed_ms`
SHALL 以注入的单调钟测量并累计为整数毫秒。

#### Scenario: 写入与重放计数

- **GIVEN** 一个新存储
- **WHEN** 成功写入 2 条 `episodic`、重放其中 1 条（同层同 id 同载荷）、再被闸门拒收 1 条
- **THEN** 快照含 `memory.writes.episodic == 2`、`memory.writes.deduped == 1`、
  `memory.writes.rejected == 1`

#### Scenario: 召回统计累计

- **GIVEN** 两次 `read()` 检索（其中一次预算截断）
- **WHEN** 读取指标快照
- **THEN** `memory.recall.calls == 2`，`candidates` / `injected` / `injected_tokens` /
  `excluded_by_budget` 为两次检索之和，且 `candidates == injected + 两类剔除`

#### Scenario: 内部打分读不计入

- **GIVEN** 一个注入了 compactor 的存储，且从未被外部检索
- **WHEN** 调用 `compact()`（内部为打分执行一次检索）
- **THEN** `memory.recall.calls == 0`

#### Scenario: 巩固耗时与失败

- **GIVEN** 注入单调钟与抛错的摘要器
- **WHEN** 调用 `compact()` 并捕获异常
- **THEN** `memory.consolidation.runs == 1`、`failures == 1`、`elapsed_ms` 为时钟差值

#### Scenario: 冲突计数

- **GIVEN** 一个新存储与一条已落库的关键事实
- **WHEN** 依次写入同值（就地刷新）与不同值（取代）
- **THEN** `memory.conflicts == 1`（同值刷新不计）

### Requirement: 记忆运维统计（memory stats）

CLI SHALL 提供 `memory stats [--json]`：**只读**聚合既有持久数据，SHALL NOT 触发复用强化、
SHALL NOT 写入任何状态。统计 SHALL 覆盖：

- `storage_bytes`：`$CORE_STATE_DIR/memory.jsonl` 的文件字节数（文件缺失 ⇒ 0）；
- 条目面（`audit(None)` 全量）：`entries_total` / `entries_active` / `entries_retracted` /
  `entries_superseded` / `entries_forgotten`，`by_layer`（仅 active）与 `by_status`（全量）；
- `conflicts`：`superseded_by` 非空的条目数（含后来被墓碑化的旧版；与当前 `status` 正交，
  change 0312）；
- `content_bytes`：active 条目正文 UTF-8 字节总和；
- 审计面（`memory.audit.jsonl`，坏行跳过、文件缺失 ⇒ 空）：`writes_by_kind`（`op="write"`）、
  `deletes_by_reason`（`op="delete"`）、`forgets_by_reason`（`op="forget"`）、
  `exports`（`op="export"` 计数）。

`--json` SHALL 输出固定键的 JSON 对象；映射字段 SHALL 按 key 排序以稳定输出。文本模式 SHALL
输出可逐行处理的摘要（含存储字节、条目数、层分布、写入分布、治理计数）。输出 SHALL NOT
包含条目正文、查询文本或密钥明文。空库 / 缺文件 SHALL 正常输出全 0 统计并以 0 退出。

#### Scenario: 全量聚合

- **GIVEN** 库内有 active / 墓碑 / 被取代条目，审计日志含写入、删除、遗忘与导出事件
- **WHEN** 执行 `memory stats --json`
- **THEN** 各计数与条目状态、审计事件一致；`storage_bytes` 等于 `memory.jsonl` 大小；
  输出不含任何正文

#### Scenario: 零强化

- **GIVEN** 库内有可被任意查询命中的条目，`reuse_count` 为 0
- **WHEN** 执行 `memory stats`
- **THEN** 所有条目 `reuse_count` 不变、无新审计写入事件

#### Scenario: 空库降级

- **GIVEN** 记忆文件与审计文件均不存在
- **WHEN** 执行 `memory stats --json`
- **THEN** 输出全 0 统计，退出码 0，不创建任何文件

#### Scenario: 冲突计数与状态正交

- **GIVEN** 一条被取代的关键事实旧版，且该旧版随后被 `retract()` 墓碑化
- **WHEN** 执行 `memory stats --json`
- **THEN** `conflicts == 1`（`entries_superseded == 0`）

## ADDED Requirements

### Requirement: 冲突可见性（memory conflicts）

CLI SHALL 提供 `memory conflicts [--json] [--limit N]`：从条目链**只读**派生冲突记录
（旧版 `superseded_by` → 新版），SHALL NOT 触发复用强化、SHALL NOT 写入任何状态。
每条记录 SHALL 包含：`entity`（由 `keyfact.<slug>[.vN]` 派生，非关键事实 id 原样）、
`old_id` / `new_id`、`old_ts` / `new_ts`（缺失版取 0）、`decision`（当前恒
`"newer_wins"`）、`old_value` / `new_value`（**脱敏**单行摘要；新版缺失 ⇒ 空）。

排序 SHALL 按新版时间降序（新版缺失时退回旧版 `ts`）；`--limit` 缺省 20、`0` 表示全部
（对齐 `memory list` / `memory audit`）。`--json` SHALL 输出上述固定键的对象数组。
文本模式 SHALL 逐行输出可处理的 `k=v` 摘要。无记录 ⇒ 输出「（无冲突记录）」并以 0 退出。
输出 SHALL NOT 包含未脱敏正文或密钥明文。本命令 SHALL 覆盖**升级前**的历史链（不依赖
审计日志是否开启或是否有 `conflict` 事件）。

本命令 SHALL NOT 提供裁决 / 合并 / 回滚动作（只读观察面）；`disputed` 状态在当前数据模型
不可达（无 `trust` / `confidence` / 显式更正信号），SHALL NOT 由本要求引入。

#### Scenario: 成对展示

- **GIVEN** 某实体经历 `v1 → v2` 的取值变化
- **WHEN** 执行 `memory conflicts`
- **THEN** 输出一条记录：`entity` 为该实体 slug、`old_id` 为 v1、`new_id` 为 v2、
  `decision=newer_wins`，且两版取值均为脱敏摘要

#### Scenario: 历史链不依赖审计

- **GIVEN** 冲突发生在审计关闭期间（无 `op="conflict"` 行），但两条版本条目仍在
- **WHEN** 执行 `memory conflicts`
- **THEN** 仍输出该条记录

#### Scenario: 零强化零写入

- **GIVEN** 存在冲突记录且相关条目 `reuse_count` 为 0
- **WHEN** 执行 `memory conflicts [--json]`
- **THEN** 所有条目 `reuse_count` 不变、无新审计写入事件、无新文件

#### Scenario: 空库

- **GIVEN** 空库
- **WHEN** 执行 `memory conflicts`
- **THEN** 输出「（无冲突记录）」、退出码 0

#### Scenario: 脱敏

- **GIVEN** 冲突两版正文中含密钥形态字符串
- **WHEN** 执行 `memory conflicts`
- **THEN** 输出中密钥已被脱敏替换，不出现明文
