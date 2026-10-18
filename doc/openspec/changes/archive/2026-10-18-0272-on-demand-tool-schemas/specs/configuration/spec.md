# configuration — 工具注入范围配置（change 0272）

## ADDED Requirements

### Requirement: 工具注入范围配置
系统 SHALL 支持配置项 `loop.tool_scope` 选择推理请求中工具参数 schema 的注入范围，并经
CLI flag `--loop.tool-scope` / 环境变量 `CORE_LOOP_TOOL_SCOPE` / config.yaml `loop.tool_scope`
三面由 ConfigSpec **单一真源**生成、参与优先级链（CLI flag > env > config.yaml > 默认值）。

合法取值为 `all` 与 `auto`（大小写不敏感、忽略首尾空白），**缺省 `auto`**。其余取值
（含原生布尔、非字符串、空串）SHALL **在校验期拒绝并阻断启动**，错误信息 SHALL 指明键名与
合法取值，SHALL NOT 静默强转或回落缺省。`all` SHALL 保持引入本键前的全量注入行为
（kill-switch）；`auto` 的注入语义见 loop「工具参数按需注入」。

#### Scenario: 缺省为 auto
- **GIVEN** config.yaml / env / CLI 均未设置 `loop.tool_scope`
- **WHEN** 系统加载配置
- **THEN** 访问器返回 `auto`

#### Scenario: 三面覆盖
- **GIVEN** `loop.tool_scope` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 按优先级链解析为归一后的 `all` 或 `auto`

#### Scenario: 非法取值阻断启动
- **GIVEN** `loop.tool_scope` 取值为 `maybe` / 空串 / 布尔 / 非字符串
- **WHEN** 系统加载配置
- **THEN** 校验失败并阻断启动，错误信息指明 `loop.tool_scope` 与合法取值（`all` / `auto`）
