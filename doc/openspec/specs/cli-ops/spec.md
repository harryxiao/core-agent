# CLI Ops Specification

## Purpose
CLI 运维命令面（cli-ops）为 core-agent 提供运维命令集与启动参数映射：以统一命令入口承载生命周期、状态、资产、连接、安全、网关六组命令，并以单一真源（ConfigSpec）驱动 CLI flag / env / config.yaml 三层参数一一对应（优先级链 CLI flag > env > config.yaml > 默认值）。

## Requirements

### Requirement: 运维命令集
系统 SHALL 提供统一的 CLI 命令集，覆盖六组：生命周期（start / stop / restart / kill）、状态（status / doctor / logs / version / help）、资产（install / uninstall / list / info）、连接（mcp add / mcp remove / mcp list）、安全（auth / permission-mode）、网关（gateway）；并 SHALL 提供一次性运维子命令：`memory maintain`（触发记忆压实与遗忘归档）、`memory list`（列出记忆条目：id / layer / kind / source / session / importance / ts / 摘要；`--limit N` 只限制展示条数，`0` 表示全部）、`memory get <id>`（打印单条全文与元数据，内容经脱敏后回显）、`memory delete <id>`（删除单条记忆：**先**把该条追加到 `$CORE_STATE_DIR/memory-deleted.jsonl`（0600）作为持久备份，备份失败即 fail-closed 不删除）、`evolve run`（强制跑一轮进化冷路径）、`rag ingest <path>`（知识文档摄取建索引）、`rag search <query>`（语义检索 top-k 片段）、`rag ask <query>`（检索片段注入生成）、`memory repair-keyfacts`（修复失效关键事实：按会话重抽 + 清理旧条目；`--dry-run` 只报告）；以上均不改变运行态、不启动常驻进程。

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

#### Scenario: 记忆检视命令
- **GIVEN** 记忆中存在若干条目
- **WHEN** 执行 `memory list` / `memory list --limit N` / `memory get <id>`
- **THEN** `list` 按固定字段顺序逐条打印；`--limit N`（`0` = 全部）只限制展示条数并在截断时提示总数；
  `get` 打印该条元数据与全文；两者输出均经 `redact_secrets` 脱敏，不回显密钥形态；
  未知 id 时 `get` 以退出码 1 结束；命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 记忆删除命令
- **GIVEN** 记忆中已存在 id 为 `<id>` 的条目
- **WHEN** 执行 `memory delete <id>`
- **THEN** 删除前把该条 JSON 追加到 `$CORE_STATE_DIR/memory-deleted.jsonl`（0600），
  再调用 `MemoryStore.discard` 删除并打印备份路径；备份写入失败时不删除任何条目并以退出码 1 结束

#### Scenario: 删除未知条目
- **GIVEN** 记忆中不存在 id 为 `<id>` 的条目
- **WHEN** 执行 `memory delete <id>`
- **THEN** 以退出码 1 结束并提示未找到，**不落备份**、不改变记忆

#### Scenario: 关键事实修复命令
- **GIVEN** 记忆中遗留 change `0173` 修复前判据产生的失效关键事实（`ref` 非 `coeffect:` 形态且取值已被抹）
- **WHEN** 执行 `memory repair-keyfacts`
- **THEN** 装配运行时后按会话重抽该会话的关键事实（材料含已归档 L4 条目）、落库新条目并清理该会话的旧条目，
  打印识别/重抽/清理条数与备份文件路径；`--dry-run` 时只报告、不删除、不落库；
  命令为一次性动作，不改变运行态、不启动常驻进程

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

一次性**任务**入口（`task <目标>`）新任务铸会话时 SHALL 经**同一**跨进程共享注册表登记
（mode `cli`，不另建第二注册表）—— 铸出的会话对 `session list` 可见、对交互入口 `--session`
续接可用；任务续跑（`--resume`）SHALL 复用检查点携带的既有会话（SHALL NOT 另铸新会话导致
同一任务轨迹分裂）。

一次性任务入口（`task <目标>`，新任务）与常驻**服务**入口（`serve`）**启动时** SHALL 扫描检查点并
**呈现**未完成任务（告警 + 提示 `task --resume <id>` 可续跑），SHALL NOT 自动重新执行未完成任务
（副作用不自动重放）；呈现 SHALL NOT 改变运行态、SHALL NOT 阻塞入口启动。任务续跑（`--resume`）
SHALL 取**时间戳最新**的检查点重建续跑状态（与崩溃恢复取最近有效检查点同口径）。

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

#### Scenario: 一次性任务入口铸会话入同一注册表
- **GIVEN** 操作者执行 `core-agent task <目标>`（新任务）
- **WHEN** 任务开始执行
- **THEN** 铸出的会话经共享注册表登记（mode `cli`），`session list` 可见；续跑 `--resume` 复用检查点既有会话而非另铸

#### Scenario: 入口启动呈现未完成任务
- **GIVEN** 存在未完成任务（检查点无 done 标记）
- **WHEN** 启动 `task` 或 `serve` 入口
- **THEN** 打印未完成任务标识与续跑提示（`task --resume <id>`），不自动重新执行、不阻塞入口启动

#### Scenario: 续跑取时间戳最新检查点
- **GIVEN** 同一任务的多个检查点，其落盘次序与时间戳次序不一致
- **WHEN** 执行 `core-agent task --resume <task-id>`
- **THEN** 取时间戳最新的检查点重建续跑状态（与崩溃恢复 restore 同口径）

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

### Requirement: 诊断视图列对齐

诊断源的**全部**列表型视图 —— `render_sessions` / `render_config` / `render_mcp` / `render_skills` /
`render_notes` / `collect_status` —— 在等宽终端下各数据列 SHALL 对齐。列宽 SHALL 按**显示宽度**计算
（东亚宽 / 全角字符按 2 列计、其余按 1 列），SHALL NOT 按字符数（`len()`）计算 —— 按字符数补齐时
含中日韩字符的清单列起点仍随内容错位（一条中文标题会把后列整体推右）。列间分隔符 SHALL 为两个空格，
SHALL NOT 使用制表符（`\t`，其宽度由终端自定，正是本次缺陷的根源）。

视图分两形态，各自的对齐口径：

- **表格型**（多行多列：会话 / MCP 端点 / 笔记）：**每列**按列内最长显示宽度补齐；
- **键值型**（一组 `标签 值` 行：配置 / 技能 / 运行状态）：**标签列**按标签中最长显示宽度补齐。

对齐 SHALL NOT 改变各行取值（只补空白）、SHALL NOT 改变 `Report` 接口与各视图签名。

#### Scenario: 笔记清单等宽列

- **WHEN** 笔记库存在多条笔记且 note_id / title 长度不一
- **THEN** `render_notes` 输出的每行中 note_id、title 列分别按清单内最长**显示宽度**补齐对齐
- **AND** 列间分隔符为两个空格，行内容不包含制表符（`\t`）

#### Scenario: 含中日韩字符的清单仍对齐

- **WHEN** 清单内某条笔记的 title 含中日韩宽字符（其显示宽度大于字符数）
- **THEN** 各行时间戳列的**起始显示列**一致（按字符数补齐会使该行整体右移）

#### Scenario: title 回退对齐

- **WHEN** 某笔记 title 为空而 note_id 较长
- **THEN** 该行 title 回退显示 note_id，且回退后 title 列宽不小于清单内最长 title

#### Scenario: 会话与 MCP 端点清单等宽列

- **WHEN** 会话注册表 / MCP 端点表存在多行且各列长度不一
- **THEN** 各行同一列的**起始显示列**一致（每列按列内最长显示宽度补齐）
- **AND** 列间分隔符为两个空格，行内容不包含制表符（`\t`）

#### Scenario: 键值型视图标签列对齐

- **WHEN** 配置 / 技能 / 运行状态视图输出多行 `标签 值`
- **THEN** 各行**值的起始显示列**一致（标签列按标签中最长显示宽度补齐）
- **AND** 行内容不包含制表符（`\t`）；技能视图的逐条明细行（`· …`）原样透出、不参与补齐

### Requirement: 记忆维护命令的时间上限

`memory maintain` SHALL 接受可选参数 `--timeout S`（单位**秒**，须为 `> 0` 的整数，
**缺省 `120`**）。命令 SHALL 以 `deadline = 当前单调时钟 + S` 调用记忆压实，并在遗忘归档前
再次检查截止时间：

- 截止后 SHALL NOT 发起新的模型调用，SHALL NOT 执行尚未开始的步骤；
- 命令 SHALL 正常退出（退出码 `0`），并明示「已达到时间上限（部分步骤已跳过）」；
- 非法 `--timeout`（`0` / 负数 / 非整数）SHALL 由参数解析拒绝（argparse 退出码 `2`），
  SHALL NOT 静默回落缺省。

命令仍为一次性动作：不改变运行态、不启动常驻进程。

#### Scenario: 缺省上限

- **GIVEN** 未传 `--timeout`
- **WHEN** 执行 `memory maintain`
- **THEN** 以 120 秒截止时间调用压实，并打印归档条数

#### Scenario: 自定义上限

- **GIVEN** 传入 `--timeout 5`
- **WHEN** 执行 `memory maintain`
- **THEN** 压实收到的截止时间约为当前时刻 + 5 秒

#### Scenario: 截止后跳过遗忘并明示

- **GIVEN** 压实执行超过 `--timeout`
- **WHEN** 命令继续执行
- **THEN** 不执行遗忘归档（或仅执行未越界的部分），打印「已达到时间上限（部分步骤已跳过）」，
  退出码为 `0`

#### Scenario: 非法上限拒绝

- **GIVEN** 传入 `--timeout 0` / `--timeout -1` / `--timeout abc`
- **WHEN** 执行命令
- **THEN** argparse 以退出码 `2` 拒绝，不执行任何维护动作
