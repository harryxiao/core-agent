# Spec Delta — memory（0306 写入幂等重放）

## ADDED Requirements

### Requirement: 写入的幂等重放

`MemoryStore.write(layer, entry)` SHALL 在以下条件**全部**成立时按幂等重放处理：同层已存在同
`id` 的条目，且入参与既有条目的**语义载荷**相同 —— `content`、`tags`、`source`、`trace_id`、
`session_id`、`kind`、`status`、`version`、`parent_id`、`superseded_by` 逐项相等。
`reuse_count` 与 `importance` SHALL NOT 参与相等判定（前者是累积证据，后者由重要度闸门写回、
不是调用方载荷）；入参 `ts <= 0`（未指定）SHALL NOT 参与判定，入参显式给值时 MUST 相等。

幂等重放 SHALL 直接返回既有条目 id，并 SHALL NOT 落盘、记录可逆效应、通知 `write_observer` 或
执行重要度评分；既有条目的 `reuse_count`、`ts` 与其余字段 SHALL 保持不变。

同 `id` 但语义载荷不同 SHALL 按既有覆盖语义写入（不合并字段、不保留旧载荷）；不同 `id` 的相同
正文 SHALL 各自成条 —— 本要求 SHALL NOT 引入内容指纹级跨 id 去重（不同 trace 的同文事件是不同
证据）。

#### Scenario: 同载荷重放零副作用

- **GIVEN** 一条已写入的条目，且其 `reuse_count` 已因检索强化而大于 0
- **WHEN** 以相同语义载荷（`ts=0`）再次 `write` 同一层同一 id
- **THEN** 返回既有 id；条目仍为一条，`reuse_count` 与 `ts` 不变；`memory.write` 效应数不增，
  `write_observer` 不被调用，评分器不被调用

#### Scenario: 不同载荷仍覆盖

- **GIVEN** 同 id 的既有条目
- **WHEN** 以不同正文或不同标签再次写入
- **THEN** 条目按新载荷覆盖，并记录新的 `memory.write` 效应（不误判为重放）

#### Scenario: 同文不同 id 不合并

- **GIVEN** 两个不同 id、正文完全相同的条目
- **WHEN** 依次写入
- **THEN** 两条均存在（幂等键是逻辑 id，不是内容）

#### Scenario: 轮次与压实重放不增殖

- **GIVEN** 已写入一轮记忆并完成一次会话压实的存储
- **WHEN** 以同一 trace 重放 `remember`、以同一会话重放 `compact`
- **THEN** 条目集合与本次 trace 的效应数均不增加
