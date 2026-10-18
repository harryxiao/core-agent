## ADDED Requirements

### Requirement: 无人值守配置项

系统 SHALL 将无人值守护栏纳入 ConfigSpec 单一真源，三面（CLI flag / env / config.yaml）
一一对应并参与优先级链（CLI flag > env > config.yaml > 默认值）：

- `permission.auto_approve_coeffects`（`--permission.auto-approve-coeffects` /
  `CORE_PERMISSION_AUTO_APPROVE_COEFFECTS`，默认空串）：auto-approve 档的 coeffect 允许面，
  逗号分隔；空串 SHALL 表示不限制（既有全放行行为）。
- `orchestration.task_timeout`（`--orchestration.task-timeout` /
  `CORE_ORCHESTRATION_TASK_TIMEOUT`，默认 `0`）：整任务墙钟时限秒数；`0` SHALL 表示不设限。
- `orchestration.task_token_budget`（`--orchestration.task-token-budget` /
  `CORE_ORCHESTRATION_TASK_TOKEN_BUDGET`，默认 `0`）：整任务 token 预算；`0` SHALL 表示关闭。
- `orchestration.failure_notify_file`（`--orchestration.failure-notify-file` /
  `CORE_ORCHESTRATION_FAILURE_NOTIFY_FILE`，默认空串）：失败通知 JSONL 文件路径；
  空串 SHALL 表示不落盘。

取值 SHALL 在校验期校验，非法取值 SHALL 阻断启动（不静默兜底、不退化成缺省）：
允许面条目 SHALL 形如 `namespace:action`（小写字母开头，允许数字 / `_` / `-`；空项忽略）；
`task_timeout` 与 `task_token_budget` SHALL 为 ≥0 的整数（布尔非法）；
`failure_notify_file` SHALL 为字符串（空串合法）。四项访问器 SHALL 由组合根/入口消费，
配置未加载时 SHALL 分别回落 `[]` / `0` / `0` / `""`（等价于关闭）。

#### Scenario: 缺省全关闭

- **GIVEN** 配置未声明任何无人值守项
- **WHEN** 读取四项访问器
- **THEN** 返回值 SHALL 为 `[]` / `0` / `0` / `""`
- **AND THEN** 权限判定、任务时限与失败通知行为 SHALL 与引入前逐字一致

#### Scenario: 三面取值与优先级

- **GIVEN** yaml 配置 `orchestration.task_timeout: 30`，env 设
  `CORE_ORCHESTRATION_TASK_TIMEOUT=60`，CLI 传 `--orchestration.task-timeout 90`
- **WHEN** 加载配置
- **THEN** `orchestration_task_timeout()` SHALL 返回 `90`

#### Scenario: 非法取值阻断启动

- **GIVEN** `orchestration.task_token_budget: -1`（或 `task_timeout: 2.5`、
  `permission.auto_approve_coeffects: filesystem` 缺少 `namespace:action` 形态、
  `failure_notify_file: true`）
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明具体键与合法形态

#### Scenario: 允许面解析

- **GIVEN** `permission.auto_approve_coeffects: filesystem:write, process:spawn,filesystem:write`
- **WHEN** 读取 `permission_auto_approve_coeffects()`
- **THEN** SHALL 返回 `["filesystem:write", "process:spawn"]`（去空白、去重、保序）
