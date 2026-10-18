## ADDED Requirements

### Requirement: 整任务时限与 token 预算

系统 SHALL 为无人值守任务提供整任务级护栏，两项均缺省关闭（`0`）：

- **墙钟时限** `orchestration.task_timeout`：`task` 入口（新任务、`--resume`、自动续跑与
  `--resume-all` 的逐任务执行）SHALL 以整任务流为范围施加时限（含拆解、全部波次与任务级
  判定）。超时 SHALL 终止任务流，SHALL 保留最近一次波次检查点（可由 `--resume` 续跑），
  SHALL 以非零退出码收口，并 SHALL 产生 `TASK_TIMEOUT` 失败通知（若配置了通知 sink）。
  `0` SHALL 表示不设限，行为与引入前逐字一致。
- **token 预算** `orchestration.task_token_budget`：调度器 SHALL 按任务累计各子任务执行返回的
  `LoopResult.token_used`（子循环收尾时的上下文记账估算）。累计值达到或超过正预算时，
  系统 SHALL 以 `TASK_TOKEN_BUDGET_EXCEEDED` 终止任务（`task_failed`），SHALL NOT 对越界
  子任务重试，SHALL NOT 重新拆解，任务状态 SHALL 为 `FAILED`；终态载荷 SHALL 携带
  `token_used` 与 `token_budget`。`0` SHALL 表示关闭预算，累计 SHALL NOT 影响任务结局。
  任务级累计 SHALL 在该任务任意终态/断流/取消退出时清除。

#### Scenario: 整任务超时终止

- **GIVEN** `orchestration.task_timeout=30` 且任务在 30 秒内未完成
- **WHEN** 时限到达
- **THEN** 任务流 SHALL 被取消，入口 SHALL 打印超时信息并以退出码 1 收口
- **AND THEN** 最近一次波次检查点 SHALL 保留；配置了通知 sink 时 SHALL 写入 `TASK_TIMEOUT`

#### Scenario: 时限为 0 不设限

- **GIVEN** `orchestration.task_timeout=0`
- **WHEN** 执行任意长任务
- **THEN** 系统 SHALL NOT 施加整任务时限（与引入前一致）

#### Scenario: token 预算耗尽即失败且不恢复

- **GIVEN** `orchestration.task_token_budget` 为正数，且累计 `LoopResult.token_used`
  达到该值
- **WHEN** 当前子任务执行完成
- **THEN** 任务 SHALL 以 `task_failed`（`TASK_TOKEN_BUDGET_EXCEEDED`）终止
- **AND THEN** 系统 SHALL NOT 重试该子任务、SHALL NOT 重新拆解计划

#### Scenario: 预算为 0 关闭

- **GIVEN** `orchestration.task_token_budget=0`
- **WHEN** 子任务报告的 `token_used` 任意大
- **THEN** 任务 SHALL 按既有验收/恢复语义推进，预算 SHALL NOT 改变结局

#### Scenario: 累计在终态后清除

- **GIVEN** 一个任务已到达终态（完成 / 失败 / 取消 / 断流）
- **WHEN** 同一调度器执行下一个任务
- **THEN** 新任务的 token 累计 SHALL 从 0 开始

### Requirement: 任务失败通知 sink

系统 SHALL 支持 `orchestration.failure_notify_file` 指定的本地 JSONL 通知文件（缺省空 =
关闭）。任务终态失败时 SHALL 追加**一行** JSON，字段 SHALL 包含
`ts / event / task_id / session_id / code / reason / goal`；`reason` 与 `goal` SHALL 经密钥
形态脱敏并截断（500 字符）。文件不存在时 SHALL 以 `0600` 创建（父目录按需创建）。
用户主动取消（`TASK_CANCELLED`）SHALL NOT 产生通知。写入失败 SHALL 只在 stderr 告警，
SHALL NOT 改变任务结局或退出码。通知 sink SHALL 覆盖入口超时（`TASK_TIMEOUT`）与自动续跑
失败；`serve` / TUI 等非 `task` 入口不在本要求范围内。

#### Scenario: 失败追加一行 JSON

- **GIVEN** 配置了通知文件且任务以失败终态结束
- **WHEN** 任务收口
- **THEN** 文件 SHALL 追加一行 JSONL，含 `task_id / code / reason / ts`
- **AND THEN** 再次失败 SHALL 追加第二行（不覆盖历史）

#### Scenario: 通知正文脱敏

- **GIVEN** 失败原因或任务目标含密钥形态子串
- **WHEN** 写入通知
- **THEN** 文件中 SHALL NOT 出现密钥明文（以 `<redacted>` 代替）

#### Scenario: 未配置不落盘

- **GIVEN** `orchestration.failure_notify_file` 为空
- **WHEN** 任务失败
- **THEN** 系统 SHALL NOT 创建或写入任何通知文件

#### Scenario: 主动取消不通知

- **GIVEN** 配置了通知文件且任务被用户取消（`TASK_CANCELLED`）
- **WHEN** 任务收口
- **THEN** 系统 SHALL NOT 写入通知

#### Scenario: 写入失败不影响任务结局

- **GIVEN** 通知路径不可写（如父路径为普通文件）
- **WHEN** 任务失败并尝试写通知
- **THEN** stderr SHALL 告警，任务失败结局与退出码 SHALL 保持不变
