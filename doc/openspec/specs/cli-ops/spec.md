# CLI Ops Specification

## Purpose
CLI 运维命令面（cli-ops）为 core-agent 提供运维命令集与启动参数映射：以统一命令入口承载生命周期、状态、资产、连接、安全、网关六组命令，并以单一真源（ConfigSpec）驱动 CLI flag / env / config.yaml 三层参数一一对应（优先级链 CLI flag > env > config.yaml > 默认值）。

## Requirements

### Requirement: 运维命令集
系统 SHALL 提供统一的 CLI 命令集，覆盖六组：生命周期（start / stop / restart / kill）、状态（status / doctor / logs / version / help）、资产（install / uninstall / list / info）、连接（mcp add / mcp remove / mcp list）、安全（auth / permission-mode）、网关（gateway）；并 SHALL 提供一次性运维子命令：`memory maintain`（触发记忆压实与遗忘归档）、`evolve run`（强制跑一轮进化冷路径）、`rag ingest <path>`（知识文档摄取建索引）、`rag search <query>`（语义检索 top-k 片段）、`rag ask <query>`（检索片段注入生成）；以上均不改变运行态、不启动常驻进程。

#### Scenario: 生命周期命令
- **GIVEN** core-agent 进程运行中
- **WHEN** 执行 start / stop / restart / kill
- **THEN** 对应启停 / 重启 / 强杀进程，运行状态一致

#### Scenario: 状态查询命令
- **GIVEN** core-agent 进程运行中
- **WHEN** 执行 status / doctor / logs / version / help
- **THEN** 返回运行状态 / 健康诊断 / 日志 / 版本 / 帮助，不改变运行态

#### Scenario: 记忆维护命令
- **GIVEN** 记忆中存在陈旧且低价值的 L2 episodic 条目
- **WHEN** 执行 `memory maintain`
- **THEN** 装配运行时后触发一次记忆维护（压实 + 遗忘归档），打印归档条数；命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 进化冷路径命令
- **GIVEN** 运行期已累积若干 trace（未达触发阈值）
- **WHEN** 执行 `evolve run`
- **THEN** 装配运行时后**强制**跑一轮进化冷路径并打印结局（诊断/提案或 `no_op`）；命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 知识摄取命令
- **GIVEN** 一份本地知识文档文件
- **WHEN** 执行 `rag ingest <path> --doc-id <id>`
- **THEN** 装配运行时后摄取该文档（分块 → embedding → 落盘索引）并打印块数／文档 id；同一文档再次摄取按 `content_hash` 判定为无变更（不重复重建）；命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 语义检索命令
- **GIVEN** 索引中已有若干知识文档的块
- **WHEN** 执行 `rag search <query> --top-k N`
- **THEN** 打印按相似度降序的 top-k 片段（含块 id、来源文档、得分、文本节选）；**不调用生成**（无需 LLM 配置即可运行）

#### Scenario: 检索增强生成命令
- **GIVEN** 索引中已有若干知识文档的块，且装配链可为检索增强链路提供生成器
- **WHEN** 执行 `rag ask <query>`
- **THEN** 检索片段经预算裁剪注入提示词，由 llm-provider 生成并打印答案；检索无命中时降级为纯 LLM 生成（不阻断）；生成器缺失（服务层未装配生成器）时以结构化错误 `GENERATION_UNAVAILABLE` 拒绝，CLI 打印提示并以退出码 1 结束（fail-closed，不静默给空答案）

#### Scenario: 资产与连接命令
- **GIVEN** core-agent 运行中
- **WHEN** 执行 install / uninstall / list / info 与 mcp add / mcp remove / mcp list
- **THEN** 安装 / 卸载 / 列出插件或 MCP 连接，复用插件来源与安装生命周期

#### Scenario: 安全与网关命令
- **GIVEN** core-agent 运行中
- **WHEN** 执行 auth / permission-mode / gateway
- **THEN** 对应鉴权 / 设置权限模式 / 启停本地服务网关

### Requirement: 启动参数映射
系统 SHALL 建立启动参数与配置项的一一对应：优先级链为 CLI flag > env > config.yaml > 默认值，映射关系由单一真源 ConfigSpec 声明（`--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR`）。

#### Scenario: 参数优先级
- **GIVEN** 同一配置项在 CLI flag / env / config.yaml / 默认值 多处定义
- **WHEN** 解析启动参数
- **THEN** 按 CLI flag > env > config.yaml > 默认值 取值，高优先级覆盖低优先级

#### Scenario: 一一对应映射
- **GIVEN** 一个配置项已由 ConfigSpec 声明
- **WHEN** 通过 CLI flag（如 `--foo.bar=value`）或 env（如 `CORE_AGENT_FOO_BAR`）指定
- **THEN** 二者映射到同一 config.foo.bar 配置项，无第二真源

### Requirement: 会话命令族与交互入口续聊
系统 SHALL 提供会话命令族：`session create`（新建会话并返回标识，登记于跨进程共享注册表）、
`session list`（枚举已登记会话：标识 + 模式）、`session show <session_id>`（按追加次序打印该会话的
对话转录）。`session show` 的转录 SHALL 取自与内核回灌**同一**转录存储（不另建副本、不第二真源）；
该会话**无转录**时 SHALL 明示无记录并以退出码 0 结束（SHALL NOT 伪造内容）。**未登记于注册表**的
`session_id` SHALL 被拒绝（fail-closed：非零退出码 + 明确提示），SHALL NOT 放宽既有会话校验；
三者均为一次性动作，不改变运行态、不启动常驻进程。

交互入口（无子命令进入的会话循环）SHALL 接受 `--session <session_id>` 以**续接既有会话**：该标识
有效时 SHALL 复用（**SHALL NOT** 新建会话），且该会话既有转录 SHALL 被载入续聊上下文与呈现面；
该标识未登记时 SHALL fail-closed 拒绝。未指定 `--session` 时 SHALL 新建会话（既有行为不变）。

#### Scenario: 列出与查看会话转录
- **GIVEN** 已存在一个会话且其转录含若干轮对话
- **WHEN** 依次执行 `session list` 与 `session show <session_id>`
- **THEN** `list` 列出该会话标识与模式；`show` 按追加次序打印该会话的转录内容

#### Scenario: 查看无转录的会话
- **GIVEN** 一个已登记但尚无对话记录的会话
- **WHEN** 执行 `session show <session_id>`
- **THEN** 明示该会话无对话记录，并以退出码 0 结束（不伪造内容）

#### Scenario: 查看未登记会话被拒
- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 执行 `session show <session_id>`
- **THEN** 拒绝并提示该会话不存在，以非零退出码结束（fail-closed，不放宽会话校验）

#### Scenario: 交互入口续接既有会话
- **GIVEN** 一个已登记的会话，其转录已有若干轮
- **WHEN** 以 `--session <session_id>` 进入交互入口
- **THEN** 复用该会话标识（不新建），其既有转录被载入续聊上下文与呈现面

#### Scenario: 交互入口续接未登记会话被拒
- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 以 `--session <session_id>` 进入交互入口
- **THEN** fail-closed 拒绝（不静默新建会话顶替）

### Requirement: 自检诊断（`doctor`）与运行状态（`status`）

CLI SHALL 提供 `doctor` 与 `status` 两个**只读**运维子命令：二者 SHALL NOT 改变运行态、SHALL NOT 启动
常驻进程、SHALL NOT 建立外部连接（含 MCP 连接）。

`doctor` SHALL 逐项自检并**逐条**呈现结论（`ok` / `warn` / `fail`），至少覆盖：配置可读且 schema 有效、
LLM 端点**已配置**、状态目录可写、工具与资产注册表可读。**全部项通过** ⇒ 退出码 `0`；**存在 `fail` 项** ⇒
退出码**非零**，且失败项 SHALL 逐条列明（含其名称与原因）。

`status` SHALL 打印运行概览（会话数 / 工具数 / 已安装资产数 / MCP 端点数 / 模型标识 / 循环预算），
并恒以退出码 `0` 结束（概览是信息面，不是判据）。

两项的输出 SHALL NOT 包含任何**密钥值** —— 涉及密钥的项 SHALL ONLY 呈现 `${VAR}` **引用名**与
「可解析 / 不可解析」的**布尔结论**（SHALL NOT 呈现解析结果）。密钥引用不可解析 SHALL 被报为 `fail`
项而非崩溃。

诊断结论 SHALL 由**单一**只读诊断源产出：CLI 与（后续的）其他消费面 SHALL 复用同一份产出，
SHALL NOT 各写一份检查逻辑。该诊断源 SHALL 经**依赖注入**取得全部句柄（SHALL NOT 自行装配运行时）。

#### Scenario: 自检全绿

- **GIVEN** 配置可读且 schema 有效、密钥引用可解析、状态目录可写、注册表可读
- **WHEN** 执行 `core-agent doctor`
- **THEN** 逐项列出检查结论且每项为 `ok`，退出码为 `0`

#### Scenario: 存在失败项时非零退出

- **GIVEN** 某检查项不通过（如 LLM 密钥引用**不可解析**，或配置缺失）
- **WHEN** 执行 `core-agent doctor`
- **THEN** 该项被呈现为 `fail` 并写明原因，退出码**非零**；其余项照常列出

#### Scenario: 诊断输出不含密钥值

- **GIVEN** 密钥引用可解析（其值存在于环境或 keychain）
- **WHEN** 执行 `core-agent doctor` 或 `core-agent status`
- **THEN** 输出中出现的只有引用名（如 `${CORE_DEEPSEEK_KEY}`）与「可解析」结论，
  **不出现**该引用的解析结果

#### Scenario: 运行状态概览

- **GIVEN** 存在若干会话与工具
- **WHEN** 执行 `core-agent status`
- **THEN** 打印会话数 / 工具数 / 已安装资产数 / MCP 端点数 / 模型标识 / 循环预算，退出码为 `0`
