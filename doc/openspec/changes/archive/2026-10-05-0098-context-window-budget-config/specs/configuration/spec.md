# Configuration Specification Delta

## MODIFIED Requirements

### Requirement: LLM 提供商配置（必选）
系统 SHALL 要求 LLM 配置（provider/model/endpoint/api_key）为必选项，缺失或不完整时阻断
启动并报明确错误；并 SHALL 支持**可选**子项 `embedding_model`（复用 `endpoint` 与密钥
引用）用于记忆检索的向量化，未设置或不可达时记忆检索回退词法，不影响启动；并 SHALL 支持
**可选**子项 `context_window`（模型上下文窗口，正整数，`0` = 未配置）作为 token 预算的派生来源
（派生口径见 loop「错误与预算控制」），未配置时回落内置缺省，不影响启动。

#### Scenario: 缺失 LLM 配置阻断启动
- **GIVEN** config.yaml 缺少 llm 段或 api_key 未解析
- **WHEN** 系统启动加载配置
- **THEN** 启动失败，报明确错误指明缺失的 LLM 配置项

#### Scenario: LLM 配置完整正常启动
- **GIVEN** llm 段包含 provider/model/endpoint/api_key 且 api_key 经 env 引用解析成功
- **WHEN** 系统启动加载配置
- **THEN** 系统正常启动并初始化 LLM 客户端

#### Scenario: 配置 embedding 模型启用语义检索
- **GIVEN** llm 段设置 `embedding_model`
- **WHEN** 系统启动装配记忆
- **THEN** 以该模型构造 embedding 客户端并注入 `MemoryStore`（经单条→批量适配器）

#### Scenario: 未配置 embedding 模型回退词法
- **GIVEN** llm 段未设置 `embedding_model`
- **WHEN** 系统启动装配记忆
- **THEN** 记忆检索不注入 embedder，回退词法相似，启动不受影响

#### Scenario: context_window 经配置链解析
- **GIVEN** `llm.context_window` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 按优先级链（CLI flag > env > config.yaml > 默认值）解析为整数，供预算派生消费

#### Scenario: context_window 非法取值被拒
- **GIVEN** `llm.context_window` 取值为负数 / 小数 / 布尔 / 非数值
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（`0` 或 ≥1 的整数）

## ADDED Requirements

### Requirement: 循环预算配置
系统 SHALL 将执行循环的预算参数纳入 ConfigSpec 单一真源：`loop.max_rounds`（单任务最大循环次数，
默认 `10`）与 `loop.output_reserve`（输出预留 token，默认 `8192`）。两项 SHALL 经 CLI flag / env /
config.yaml 三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。
两项取值 SHALL 在校验期校验（`loop.max_rounds` 须为 ≥1 的整数、`loop.output_reserve` 须为 ≥0 的整数，
布尔值非法），并 SHALL 与 `llm.context_window` **交叉校验**：两者同时配置时
`llm.context_window` SHALL 大于 `loop.output_reserve`，否则校验失败并阻断启动。

#### Scenario: 预算参数经 ConfigSpec 声明
- **GIVEN** 配置了 loop 段的 max_rounds / output_reserve
- **WHEN** 系统启动加载配置
- **THEN** 两项经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省取内置默认值
- **GIVEN** loop 段未配置
- **WHEN** 系统启动加载配置
- **THEN** `loop.max_rounds` 取 `10`、`loop.output_reserve` 取 `8192`，系统正常启动

#### Scenario: CLI 覆盖 env 与 yaml
- **GIVEN** `loop.output_reserve` 在 CLI flag、env 与 config.yaml 中均有定义
- **WHEN** 系统加载配置
- **THEN** CLI flag 值最高优先，覆盖 env 与 yaml 值

#### Scenario: 非法取值校验期拒绝
- **GIVEN** `loop.max_rounds` 取 `0` / `loop.output_reserve` 取负数，或任一取布尔 / 非整数
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（不静默强转、不退化成缺省）

#### Scenario: 窗口与预留交叉校验
- **GIVEN** `llm.context_window` 已配置且不大于 `loop.output_reserve`
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明上下文窗口不敷输出预留
