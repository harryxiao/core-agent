## MODIFIED Requirements

### Requirement: 任务失败通知 sink

系统 SHALL 支持 `orchestration.failure_notify_file` 指定的本地 JSONL 通知文件（缺省空 =
关闭）。任务终态失败时 SHALL 追加**一行** JSON，字段 SHALL 包含
`ts / event / task_id / session_id / code / reason / goal`；`reason` 与 `goal` SHALL 经密钥
形态脱敏并截断（500 字符）。文件不存在时 SHALL 以 `0600` 创建（父目录按需创建）。
用户主动取消（`TASK_CANCELLED`）SHALL NOT 产生通知。写入失败 SHALL 只在 stderr 告警，
SHALL NOT 改变任务结局或退出码。通知 sink SHALL 覆盖入口超时（`TASK_TIMEOUT`）与自动续跑
失败；`serve` / TUI 等非 `task` 入口不在本要求范围内。

系统 SHALL 另支持 `orchestration.failure_notify_webhook` 指定的 HTTP(S) 远程 sink（缺省空 =
关闭）。启用时 SHALL 在任务失败收口以 `POST`、`Content-Type: application/json` 发送一份
JSON，字段 SHALL 包含 `text / event / task_id / session_id / code / reason / goal`；
`reason` 与 `goal` SHALL 经同一脱敏与截断。请求 SHALL 有界（5 秒）且为单次尝试；
失败 SHALL 只在 stderr 告警（SHALL NOT 回显 URL），SHALL NOT 改变任务结局或退出码。
两个 sink SHALL 相互独立：任一失败 SHALL NOT 阻止另一个写入。取消语义与文件 sink 相同。

#### Scenario: 失败追加一行 JSON

- **GIVEN** 配置了通知文件且任务以失败终态结束
- **WHEN** 任务收口
- **THEN** 文件 SHALL 追加一行 JSONL，含 `task_id / code / reason / ts`
- **AND THEN** 再次失败 SHALL 追加第二行（不覆盖历史）

#### Scenario: 通知正文脱敏

- **GIVEN** 失败原因或任务目标含密钥形态子串
- **WHEN** 写入通知
- **THEN** 文件中 SHALL NOT 出现密钥明文（以 `<redacted>` 代替）
- **AND THEN** 启用了 webhook 时请求体 SHALL 同样不含密钥明文

#### Scenario: 未配置不落盘

- **GIVEN** `orchestration.failure_notify_file` 为空
- **WHEN** 任务失败
- **THEN** 系统 SHALL NOT 创建或写入任何通知文件

#### Scenario: 主动取消不通知

- **GIVEN** 配置了通知文件且任务被用户取消（`TASK_CANCELLED`）
- **WHEN** 任务收口
- **THEN** 系统 SHALL NOT 写入通知，SHALL NOT 发起 webhook 请求

#### Scenario: 写入失败不影响任务结局

- **GIVEN** 通知路径不可写（如父路径为普通文件）
- **WHEN** 任务失败并尝试写通知
- **THEN** stderr SHALL 告警，任务失败结局与退出码 SHALL 保持不变

#### Scenario: webhook 推送失败不影响任务结局

- **GIVEN** 配置了 webhook 且接收端不可用（连接失败 / 超时 / 非 2xx）
- **WHEN** 任务失败并尝试推送
- **THEN** stderr SHALL 告警且不含 URL 值，任务结局与退出码 SHALL 保持不变
- **AND THEN** 若同时配置了通知文件，文件 SHALL 已正常写入

#### Scenario: 未配置 webhook 不发起请求

- **GIVEN** `orchestration.failure_notify_webhook` 为空
- **WHEN** 任务失败
- **THEN** 系统 SHALL NOT 发起任何网络请求
