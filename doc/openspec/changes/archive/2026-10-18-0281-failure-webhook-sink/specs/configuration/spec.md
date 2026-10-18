## ADDED Requirements

### Requirement: 失败通知 webhook 配置

系统 SHALL 将 `orchestration.failure_notify_webhook` 纳入 ConfigSpec 单一真源，三面
（CLI flag `--orchestration.failure-notify-webhook` / env
`CORE_ORCHESTRATION_FAILURE_NOTIFY_WEBHOOK` / config.yaml）一一对应并参与优先级链
（CLI > env > config.yaml > 默认值）。默认值 SHALL 为空串，表示不推送（行为与引入前一致）。

非空取值 SHALL 为 `http` 或 `https` 的绝对 URL（scheme 与 host 均非空）；其他 scheme
（含 `file` / `ftp`）、缺 host、非字符串取值 SHALL 在校验期判为错误并**阻断启动**。
错误信息 SHALL 指明键名与合法形态，SHALL NOT 回显 URL 值（URL 可能内嵌令牌）。
访问器 `orchestration_failure_notify_webhook()` SHALL 在配置未加载时回落空串。

#### Scenario: 缺省不推送

- **GIVEN** 配置未声明 `orchestration.failure_notify_webhook`
- **WHEN** 读取 `orchestration_failure_notify_webhook()`
- **THEN** SHALL 返回空串，任务失败时 SHALL NOT 发起任何网络请求

#### Scenario: 三面取值与优先级

- **GIVEN** yaml 配置 webhook A，env 配置 webhook B，CLI 传 webhook C
- **WHEN** 加载配置
- **THEN** `orchestration_failure_notify_webhook()` SHALL 返回 C

#### Scenario: 非法 URL 阻断启动

- **GIVEN** `orchestration.failure_notify_webhook` 为 `file:///tmp/x`（或 `ftp://h/x`、
  `https://`、布尔值）
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明键名与 `http(s)` 形态
- **AND THEN** 错误信息 SHALL NOT 包含该 URL 的值
