# loop — 工具参数按需注入（change 0272）

## ADDED Requirements

### Requirement: 工具参数按需注入
系统 SHALL 按配置项 `loop.tool_scope` 选择**随推理请求发送的工具参数 schema**（`LLMRequest.tools`），
取值语义：

- `all`：SHALL 恒注入全部已注册工具的 schema，行为与引入本机制前**逐字一致**。
- `auto`（缺省）：当已注册工具数 **≤ 8** 或 `tools.schema_read` **未注册**时，SHALL 注入全部
  （小工具面免加载 / 不得造出模型无法加载参数的不可达工具面）；否则 SHALL 只注入
  **核心工具集**（`tools.file_read`、`tools.file_write`、`tools.file_patch`、`tools.code_run`、
  `tools.web_fetch`、`tools.context_read`、`tools.delegate`）、**本回合已加载工具**与
  `tools.schema_read`。

系统提示中的**可用工具目录**（工具 id + 描述）SHALL 始终列出全部已注册工具，SHALL NOT 随
`loop.tool_scope` 收窄。`auto` 生效时，该目录 SHALL 附带一行说明：未注入参数 schema 的工具
须先经 `tools.schema_read` 获取参数（下一轮生效）；`all` 时 SHALL NOT 附带该行（提示词逐字不变）。

循环 SHALL 把 `tools.schema_read` **成功**执行且请求的、已注册的工具 id 吸收进本轮上下文包的
`loaded_tools` 集合，SHALL 自**下一轮**推理起生效；该集合 SHALL 为**回合内**状态，新回合
SHALL 从核心工具集重新开始（不清洗、不写记忆、不跨会话）。

本机制 SHALL 只影响请求侧 schema 注入，SHALL NOT 影响工具执行面：参数校验 / 权限分级 /
coeffect 解析 / 确认门 / 撤销与去重 SHALL 继续以**全部已注册工具**为真源；未注入 schema 的
工具 SHALL 仍可经文本 JSON 动作调用（不构成访问控制）。

#### Scenario: 缺省按需注入主工具面
- **GIVEN** 已注册工具数大于 8 且 `tools.schema_read` 已注册，`loop.tool_scope` 为缺省 `auto`
- **WHEN** 规划器为一轮推理组装请求
- **THEN** `LLMRequest.tools` 只含核心工具集、本回合已加载工具与 `tools.schema_read`，
  不含 `tools.gate_run` / `tools.process` / `tools.install` / `tools.tasks` 等按需工具

#### Scenario: 小工具面注入全部
- **GIVEN** 已注册工具数不超过 8（如子 Agent 的内置七件），`loop.tool_scope` 为 `auto`
- **WHEN** 规划器组装请求
- **THEN** 全部已注册工具 schema 均被注入（免加载）

#### Scenario: schema_read 未注册时回落全量
- **GIVEN** 已注册工具数大于 8，但工具面未注册 `tools.schema_read`
- **WHEN** 规划器在 `auto` 下组装请求
- **THEN** 注入全部已注册工具 schema（不得出现模型看不见参数的不可达工具）

#### Scenario: 加载后下一轮可见
- **GIVEN** 一轮推理产出对 `tools.schema_read` 的调用并成功执行，请求了 `tools.process`
- **WHEN** 循环执行下一轮推理
- **THEN** 该轮 `LLMRequest.tools` 含 `tools.process` 的参数 schema

#### Scenario: 新回合重置已加载集合
- **GIVEN** 上一回合已加载若干按需工具并结束
- **WHEN** 同一会话发起新回合（新建上下文包）
- **THEN** 已加载集合为空，新回合请求重新只含核心工具集与 `tools.schema_read`

#### Scenario: all 模式保持全量
- **GIVEN** `loop.tool_scope` 为 `all`
- **WHEN** 规划器组装请求
- **THEN** 注入全部已注册工具 schema，且系统提示不附带按需加载说明行（与引入前逐字一致）

#### Scenario: 工具目录不随开关收窄
- **GIVEN** `auto` 生效且请求只注入核心工具集
- **WHEN** 规划器装配系统提示
- **THEN** 「可用工具」目录仍列出全部已注册工具（id + 描述），并附带按需加载说明行

#### Scenario: 请求侧收窄不构成访问控制
- **GIVEN** `auto` 生效且某按需工具的参数 schema 未注入
- **WHEN** 模型经文本 JSON 动作直接调用该工具
- **THEN** 工具照常经过参数校验、权限、coeffect 与确认门并执行（执行面不受影响）

#### Scenario: 未知工具 id 的加载不阻断
- **GIVEN** 模型请求加载一个未注册的工具 id
- **WHEN** `tools.schema_read` 执行
- **THEN** 该 id 记入 `unknown` 返回，不抛错、不吸收进已加载集合，本轮继续
