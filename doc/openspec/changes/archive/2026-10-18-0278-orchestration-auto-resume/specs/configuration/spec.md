## MODIFIED Requirements

### Requirement: 编排调度配置
系统 SHALL 将编排调度策略纳入 ConfigSpec 单一真源：`orchestration.difficulty_policy`（同波次调度策略，默认 `off`，可选 `off` / `difficulty`）、`orchestration.max_concurrency`（波次并发上限，默认 `4`）、`orchestration.subtask_timeout`（子任务交接超时秒数，默认 `600`；显式 `0` 表示不设限）与 `orchestration.auto_resume`（未完成任务启动自动续跑，默认 `false`）。四项 SHALL 经 CLI flag / env / config.yaml 三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。取值 SHALL 在校验期校验：`orchestration.max_concurrency` 须为 ≥1 的整数（布尔非法），`orchestration.difficulty_policy` 须为 `off` / `difficulty` 之一，`orchestration.subtask_timeout` 须为 ≥0 的整数（布尔非法），`orchestration.auto_resume` 须为布尔或 `true`/`false` 字符串，否则校验失败并阻断启动（不静默强转、不退化成缺省）。`orchestration.subtask_timeout` 的非零值 SHALL 由组合根注入调度器并生效为交接 deadline；`0` 值 SHALL 同样由组合根注入，语义为不设 deadline。`orchestration.auto_resume` 的取值 SHALL 由 `task` 入口读取并决定是否执行启动自动续跑。

#### Scenario: 编排键经 ConfigSpec 声明
- **GIVEN** 配置了 orchestration 段的 difficulty_policy / max_concurrency / subtask_timeout / auto_resume
- **WHEN** 系统启动加载配置
- **THEN** 四项经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省取内置默认值
- **GIVEN** orchestration 段未配置
- **WHEN** 系统启动加载配置
- **THEN** `orchestration.difficulty_policy` 取 `off`、`orchestration.max_concurrency` 取 `4`、`orchestration.subtask_timeout` 取 `600`、`orchestration.auto_resume` 取 `false`，系统正常启动

#### Scenario: 显式 0 仍表示不设限
- **GIVEN** `orchestration.subtask_timeout` 显式配置为 `0`
- **WHEN** 系统启动加载配置并装配调度器
- **THEN** 调度器注入值为 `0`，交接不设 deadline（校验放行，不回退为缺省 `600`）

#### Scenario: 非法取值校验期拒绝
- **GIVEN** `orchestration.max_concurrency` 取 `0` / 负数 / 布尔 / 非整数，或 `orchestration.difficulty_policy` 取集合外的字符串，或 `orchestration.subtask_timeout` 取负数 / 布尔 / 非整数，或 `orchestration.auto_resume` 取非布尔值（如 `maybe`）
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值，不静默强转、不退化成缺省
