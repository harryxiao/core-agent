## MODIFIED Requirements

### Requirement: 循环预算配置
系统 SHALL 将执行循环的预算参数纳入 ConfigSpec 单一真源：`loop.max_rounds`（单任务最大循环次数，
默认 `20`）与 `loop.output_reserve`（输出预留 token，默认 `8192`）与 `loop.history_turns`（回灌最近 N 轮对话历史，默认 `20`，`0` 表示关闭回灌）与 `loop.compact_steps`（**本轮工具步数**达此值触发上下文压实，默认 `6`）。四项 SHALL 经 CLI flag / env /
config.yaml 三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。
四项取值 SHALL 在校验期校验（`loop.max_rounds` 须为 ≥1 的整数、`loop.output_reserve` 须为 ≥0 的整数、`loop.history_turns` 须为 ≥0 的整数、
`loop.compact_steps` 须为 ≥1 的整数，布尔值非法），并 SHALL 与 `llm.context_window` **交叉校验**：两者同时配置时
`llm.context_window` SHALL 大于 `loop.output_reserve`，否则校验失败并阻断启动。

#### Scenario: 预算参数经 ConfigSpec 声明
- **GIVEN** 配置了 loop 段的 max_rounds / output_reserve
- **WHEN** 系统启动加载配置
- **THEN** 两项经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省取内置默认值
- **GIVEN** loop 段未配置
- **WHEN** 系统启动加载配置
- **THEN** `loop.max_rounds` 取 `20`、`loop.output_reserve` 取 `8192`、`loop.history_turns` 取 `20`、`loop.compact_steps` 取 `6`，系统正常启动

#### Scenario: CLI 覆盖 env 与 yaml
- **GIVEN** `loop.output_reserve` 在 CLI flag、env 与 config.yaml 中均有定义
- **WHEN** 系统加载配置
- **THEN** CLI flag 值最高优先，覆盖 env 与 yaml 值

#### Scenario: 非法取值校验期拒绝
- **GIVEN** `loop.max_rounds` 取 `0` / `loop.output_reserve` 取负数，或任一取布尔 / 非整数
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（不静默强转、不退化成缺省）

#### Scenario: 回灌轮数经 ConfigSpec 声明且受校验

- **GIVEN** `loop.history_turns` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 该值经 ConfigSpec 单一真源解析；取负数 / 小数 / 布尔 / 非数值时校验失败并阻断启动

#### Scenario: 压实步数阈值经 ConfigSpec 声明且受校验

- **GIVEN** `loop.compact_steps` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 该值经 ConfigSpec 单一真源解析并注入组合根构造的压实器；取 `0` / 负数 / 小数 / 布尔 /
  非数值时校验失败并阻断启动

#### Scenario: 窗口与预留交叉校验
- **GIVEN** `llm.context_window` 已配置且不大于 `loop.output_reserve`
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明上下文窗口不敷输出预留

### Requirement: 编排调度配置
系统 SHALL 将编排调度策略纳入 ConfigSpec 单一真源：`orchestration.difficulty_policy`（同波次调度策略，默认 `off`，可选 `off` / `difficulty`）、`orchestration.max_concurrency`（波次并发上限，默认 `4`）与 `orchestration.subtask_timeout`（子任务交接超时秒数，默认 `600`；显式 `0` 表示不设限）。三项 SHALL 经 CLI flag / env / config.yaml 三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。取值 SHALL 在校验期校验：`orchestration.max_concurrency` 须为 ≥1 的整数（布尔非法），`orchestration.difficulty_policy` 须为 `off` / `difficulty` 之一，`orchestration.subtask_timeout` 须为 ≥0 的整数（布尔非法），否则校验失败并阻断启动（不静默强转、不退化成缺省）。`orchestration.subtask_timeout` 的非零值 SHALL 由组合根注入调度器并生效为交接 deadline；`0` 值 SHALL 同样由组合根注入，语义为不设 deadline。

#### Scenario: 编排键经 ConfigSpec 声明
- **GIVEN** 配置了 orchestration 段的 difficulty_policy / max_concurrency / subtask_timeout
- **WHEN** 系统启动加载配置
- **THEN** 三项经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省取内置默认值
- **GIVEN** orchestration 段未配置
- **WHEN** 系统启动加载配置
- **THEN** `orchestration.difficulty_policy` 取 `off`、`orchestration.max_concurrency` 取 `4`、`orchestration.subtask_timeout` 取 `600`，系统正常启动

#### Scenario: 显式 0 仍表示不设限
- **GIVEN** `orchestration.subtask_timeout` 显式配置为 `0`
- **WHEN** 系统启动加载配置并装配调度器
- **THEN** 调度器注入值为 `0`，交接不设 deadline（校验放行，不回退为缺省 `600`）

#### Scenario: 非法取值校验期拒绝
- **GIVEN** `orchestration.max_concurrency` 取 `0` / 负数 / 布尔 / 非整数，或 `orchestration.difficulty_policy` 取集合外的字符串，或 `orchestration.subtask_timeout` 取负数 / 布尔 / 非整数
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值，不静默强转、不退化成缺省
