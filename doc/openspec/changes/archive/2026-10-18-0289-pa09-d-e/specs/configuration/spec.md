# configuration — PA-09 E：语义检索可强制（change 0289）

## MODIFIED Requirements

### Requirement: LLM 提供商配置（必选）
系统 SHALL 要求 LLM 配置（provider/model/endpoint/api_key）为必选项，缺失或不完整时阻断
启动并报明确错误；并 SHALL 支持**可选**子项 `embedding_model`（复用 `endpoint` 与密钥
引用）用于记忆检索的向量化，并 SHALL 支持**可选**子项 `embedding_auto`（端点推导开关，
**缺省 `true`**）：显式 `embedding_model` 永远优先；未显式配置且 `embedding_auto` 开启时，
SHALL 按 `endpoint` 主机从**内置已知端点表**推导默认 embedding 模型（精确或子域匹配，
大小写不敏感），表中未命中 SHALL 不推导（有效模型为空）；`embedding_auto` 关闭时 SHALL NOT
推导。`embedding_required` 关闭时，有效 embedding 模型为空或不可达时记忆检索回退词法，
不影响启动；`embedding_auto`
取值口径与 feature flag **同集**（原生布尔与 `true/false`·`yes/no`·`on/off`·`1/0`，大小写
不敏感、忽略首尾空白），其余取值 SHALL **在校验期拒绝并阻断启动**（错误信息指明键名与
合法取值），SHALL NOT 静默强转。并 SHALL 支持**可选**子项 `embedding_required`
（**缺省 `false`**）：开启时，若**有效 embedding 模型为空**（既未显式配置
`embedding_model`，也未能按 `embedding_auto` 从端点推导），系统 SHALL 在**配置校验期**
阻断启动并报明确错误（错误信息指明键名与可操作提示，SHALL NOT 回显 `endpoint` 或密钥）；
显式模型或端点推导命中任一存在即视为满足。该开关只保证「模型已确定」，SHALL NOT 探测
网络可达性——调用期失败仍按既有路径降级词法。`embedding_required` 取值口径与
`embedding_auto` **同集**，其余取值 SHALL 在校验期拒绝并阻断启动，SHALL NOT 静默强转；
关闭（缺省）时行为与引入前**逐字一致**。并 SHALL 支持
**可选**子项 `context_window`（模型上下文窗口，正整数，`0` = 未配置）作为 token 预算的派生来源
（派生口径见 loop「错误与预算控制」），未配置时 SHALL **按 `model` 从内置已知模型窗口表推导**
（子串匹配，大小写不敏感），表中未命中 SHALL 回落内置缺省，不影响启动；并 SHALL 支持
**可选**子项 `show_thinking`（思考回显开关，**缺省 `false`**）：取值口径与 feature flag
**同集**（原生布尔与 `true/false`·`yes/no`·`on/off`·`1/0`，大小写不敏感、忽略首尾空白），
其余取值 SHALL **在校验期拒绝并阻断启动**（错误信息指明键名与合法取值），SHALL NOT 静默强转。
开启后方经事件面外发思考原文（口径见 llm-provider「默认实现与配置归一化」与 loop「异步流式执行」）；
关闭时系统 SHALL NOT 产出思考事件、三端 SHALL NOT 呈现思考块（行为与既有缺省逐字一致）。
并 SHALL 支持**可选**子项 `timeout`（单次模型调用超时上限，单位**秒**，须 `> 0`，**缺省 `60.0`**）
与 **可选**子项 `max_retries`（调用失败的最大重试次数，须为 `≥ 0` 的**整数**，**缺省 `3`**）：
两者 SHALL 经 CLI flag / env / config.yaml 三面由 ConfigSpec 单一真源生成、参与优先级链
（CLI flag > env > config.yaml > 默认值），解析后由组合根注入 LLM 实现（生效口径见 llm-provider
「模型调用可靠性」）；未配置时 SHALL 取与实现类缺省**逐字一致**的值（`60.0` / `3`），行为零改变。
两者取值 SHALL 在校验期校验并 SHALL NOT 静默强转：`timeout` 取≤ 0 / 非数值 / 布尔，
`max_retries` 取负数 / 小数 / 布尔 / 非数值时 SHALL **阻断启动**并报明确错误（指明键名与合法取值）。

窗口来源的**优先级** SHALL 为：`llm.context_window`（显式配置，`> 0`）**优先于**内置表推导；
显式配置 SHALL NOT 被表值覆盖（用户显式声明永远胜出）。内置表 SHALL 只覆盖**有据可查**的常见模型族
（每项为「模型名子串 → 窗口」并附来源口径），SHALL NOT 猜测未收录模型；表自身 SHALL NOT 引入配置键
（不新增 CLI / env / yaml 面，SHALL NOT 成为第二真源）。

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

#### Scenario: 未配置时按端点推导默认 embedding 模型
- **GIVEN** llm 段未设置 `embedding_model`（或为空），`embedding_auto` 为缺省开启，
  且 `endpoint` 主机命中内置端点表（如 `open.bigmodel.cn`）
- **WHEN** 系统启动装配记忆
- **THEN** 有效 embedding 模型取该端点的默认模型（如 `embedding-3`），并以之构造 embedding
  客户端注入 `MemoryStore`；显式 `embedding_model` 不被推导值覆盖

#### Scenario: 未配置 embedding 模型回退词法
- **GIVEN** llm 段未设置 `embedding_model`，`embedding_required` 关闭（缺省），且 `endpoint`
  主机不在内置端点表内（如自建代理）
- **WHEN** 系统启动装配记忆
- **THEN** 有效 embedding 模型为空，记忆检索不注入 embedder，回退词法相似，启动不受影响

#### Scenario: 关闭端点推导回退词法
- **GIVEN** llm 段未设置 `embedding_model`，`embedding_auto` 显式关闭（`false`），
  且 `embedding_required` 关闭（缺省）
- **WHEN** 系统启动装配记忆
- **THEN** 有效 embedding 模型为空，记忆检索回退词法（与引入端点推导前逐字一致）

#### Scenario: embedding_auto 取值归一与非法拒绝
- **GIVEN** `llm.embedding_auto` 取值为原生布尔、`true/false`、`yes/no`、`on/off`、`1/0`
  （大小写不敏感）
- **WHEN** 系统加载配置
- **THEN** 归一为开或关；取值为 `maybe` / 空串 / 映射时校验失败并阻断启动，错误信息指明
  键名与合法取值，SHALL NOT 静默强转

#### Scenario: embedding_required 空模型阻断启动
- **GIVEN** `llm.embedding_required=true`，未显式配置 `embedding_model`，且 `endpoint` 主机
  不在内置端点表内（有效模型为空）
- **WHEN** 系统加载配置（含热更新 `apply_change`）
- **THEN** 校验失败并阻断启动 / 拒绝该次热更新；错误信息指明 `llm.embedding_required`
  与「有效 embedding 模型为空」，SHALL NOT 回显 `endpoint` 或密钥

#### Scenario: embedding_required 有确定模型时正常启动
- **GIVEN** `llm.embedding_required=true`，且显式配置了 `embedding_model`，或 `endpoint`
  主机命中内置端点表（`embedding_auto` 开启）
- **WHEN** 系统加载配置
- **THEN** 校验通过并正常启动；该开关 SHALL NOT 触发网络可达性探测

#### Scenario: embedding_required 取值归一与非法拒绝
- **GIVEN** `llm.embedding_required` 取值为原生布尔、`true/false`、`yes/no`、`on/off`、`1/0`
  （大小写不敏感）
- **WHEN** 系统加载配置
- **THEN** 归一为开或关；取值为 `maybe` / 空串 / 映射时校验失败并阻断启动，错误信息指明
  键名与合法取值，SHALL NOT 静默强转

#### Scenario: context_window 经配置链解析
- **GIVEN** `llm.context_window` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 按优先级链（CLI flag > env > config.yaml > 默认值）解析为整数，供预算派生消费

#### Scenario: context_window 非法取值被拒
- **GIVEN** `llm.context_window` 取值为负数 / 小数 / 布尔 / 非数值
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（`0` 或 ≥1 的整数）

#### Scenario: 未配置窗口时按模型推导
- **GIVEN** llm 段未配置 `context_window`（`0`），`model` 为内置表收录的模型族（如 `gpt-4o`
  或 `claude-*`）
- **WHEN** 系统派生 token 预算
- **THEN** 窗口取自内置表（该模型族的实际上下文窗口）⇒ 预算为「推导窗口 − 输出预留」，
  **不再**恒等于内置缺省 `65536`

#### Scenario: 未命中内置表回落缺省
- **GIVEN** llm 段未配置 `context_window`，`model` 不在内置表内
- **WHEN** 系统派生 token 预算
- **THEN** 窗口回落内置缺省 ⇒ 预算与变更前**逐字一致**（`65536`）

#### Scenario: 显式窗口优先于表推导
- **GIVEN** llm 段配置 `context_window: 32768`，`model` 为内置表收录且表值不同
- **WHEN** 系统派生 token 预算
- **THEN** 窗口取显式值 `32768`（**优先于**表推导），预算为 `32768 − output_reserve`

#### Scenario: show_thinking 缺省关
- **GIVEN** llm 段未声明 `show_thinking`（或整段缺省）
- **WHEN** 系统加载配置并装配循环
- **THEN** 思考回显为**关**（`show_thinking=False`）—— 事件面不产 `loop.reasoning`，三端不呈现思考块，与既有缺省**逐字一致**

#### Scenario: show_thinking 取值归一与非法拒绝
- **GIVEN** `llm.show_thinking` 取值为原生布尔、`true/false`、`yes/no`、`on/off`、`1/0`（大小写不敏感）
- **WHEN** 系统加载配置
- **THEN** 归一为**开**（真值）或**关**（假值）—— 不得因 `bool("<非空字符串>")` 为真而被当作开启；取值为 `maybe` / 空串 / 映射时校验失败并阻断启动，错误信息指明键名与合法取值

#### Scenario: 超时与重试经配置链解析且缺省不变
- **GIVEN** `llm.timeout` / `llm.max_retries` 经 CLI flag（`--llm.timeout` / `--llm.max-retries`）/
  env（`CORE_LLM_TIMEOUT` / `CORE_LLM_MAX_RETRIES`）/ config.yaml 任一面设置，或**均未设置**
- **WHEN** 系统加载配置并构造 LLM 实现
- **THEN** 按优先级链解析为 `float` / `int` 并注入实现；**均未设置**时取 `60.0` / `3`
  （与实现类缺省**逐字一致**，行为零改变）

#### Scenario: 超时与重试非法取值被拒
- **GIVEN** `llm.timeout` 取值为 `0` / 负数 / 非数值 / 布尔，或 `llm.max_retries` 取值为负数 /
  小数 / 布尔 / 非数值
- **WHEN** 系统加载配置
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（`timeout` 须 > 0，`max_retries`
  须为 ≥ 0 的整数），SHALL NOT 静默强转
