## MODIFIED Requirements

### Requirement: LLM 提供商配置（必选）
系统 SHALL 要求 LLM 配置（provider/model/endpoint/api_key）为必选项，缺失或不完整时阻断
启动并报明确错误；并 SHALL 支持**可选**子项 `embedding_model`（复用 `endpoint` 与密钥
引用）用于记忆检索的向量化，未设置或不可达时记忆检索回退词法，不影响启动；并 SHALL 支持
**可选**子项 `context_window`（模型上下文窗口，正整数，`0` = 未配置）作为 token 预算的派生来源
（派生口径见 loop「错误与预算控制」），未配置时回落内置缺省，不影响启动；并 SHALL 支持
**可选**子项 `show_thinking`（思考回显开关，**缺省 `false`**）：取值口径与 feature flag
**同集**（原生布尔与 `true/false`·`yes/no`·`on/off`·`1/0`，大小写不敏感、忽略首尾空白），
其余取值 SHALL **在校验期拒绝并阻断启动**（错误信息指明键名与合法取值），SHALL NOT 静默强转。
开启后方经事件面外发思考原文（口径见 llm-provider「默认实现与配置归一化」与 loop「异步流式执行」）；
关闭时系统 SHALL NOT 产出思考事件、三端 SHALL NOT 呈现思考块（行为与既有缺省逐字一致）。

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

#### Scenario: show_thinking 缺省关
- **GIVEN** llm 段未声明 `show_thinking`（或整段缺省）
- **WHEN** 系统加载配置并装配循环
- **THEN** 思考回显为**关**（`show_thinking=False`）—— 事件面不产 `loop.reasoning`，三端不呈现思考块，与既有缺省**逐字一致**

#### Scenario: show_thinking 取值归一与非法拒绝
- **GIVEN** `llm.show_thinking` 取值为原生布尔、`true/false`、`yes/no`、`on/off`、`1/0`（大小写不敏感）
- **WHEN** 系统加载配置
- **THEN** 归一为**开**（真值）或**关**（假值）—— 不得因 `bool("<非空字符串>")` 为真而被当作开启；取值为 `maybe` / 空串 / 映射时校验失败并阻断启动，错误信息指明键名与合法取值
