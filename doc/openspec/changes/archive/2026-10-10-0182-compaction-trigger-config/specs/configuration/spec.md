# configuration Specification Delta — 压实步数阈值配置键（change 0182）

## MODIFIED Requirements

### Requirement: 循环预算配置
系统 SHALL 将执行循环的预算参数纳入 ConfigSpec 单一真源：`loop.max_rounds`（单任务最大循环次数，
默认 `10`）与 `loop.output_reserve`（输出预留 token，默认 `8192`）与 `loop.history_turns`（回灌最近 N 轮对话历史，默认 `20`，`0` 表示关闭回灌）与 `loop.compact_steps`（**本轮工具步数**达此值触发上下文压实，默认 `6`）。四项 SHALL 经 CLI flag / env /
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
- **THEN** `loop.max_rounds` 取 `10`、`loop.output_reserve` 取 `8192`、`loop.history_turns` 取 `20`、`loop.compact_steps` 取 `6`，系统正常启动

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
