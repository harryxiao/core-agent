# UI Specification

## Purpose
UI 界面与启动模式是 core-agent 面向用户的统一呈现层：CLI / Web / Desktop 三种入口共享同一内核与同一 LLM 配置源，行为、鉴权、日志保持一致；用户在 Web 与桌面 UI 内即可配置 LLM API；桌面与 Web 复用同一前端构建产物实现体验一致；并支持图像、语音等多模态输入的统一接入。

## 技术选型
- **CLI**：Python 原生 Textual，取 Ink 的声明式 + 响应式交互哲学，同进程复刻折叠块/流式/多面板，避免 Node 桥接
- **Web**：自研单 SPA（Svelte 前端）+ 统一后端 API（HTTP + SSE）
- **Desktop**：Tauri 壳复用同一 SPA 构建产物 + sidecar 拉起 Python 后端，体积远小于 Electron
- **统一 API 解耦**：三种模式共走同一后端 API，CLI 不绕过内核直连，保证鉴权/日志/行为一致

## Requirements

### Requirement: 三模统一内核启动
系统 SHALL 提供 CLI、Web、Desktop 三种启动模式，三者共享同一内核与同一 LLM 配置源；统一后端 API 层 SHALL 以 `create_session` 生成会话标识并**无改写**透传至内核循环与记忆写入（会话归属），`compact(session_id)` SHALL 触发该会话记忆的真实压实，`get_memory(session_id)` SHALL 只返回归属于该会话的记忆条目。经 `run_task(session_id, goal)` 派发的编排任务 SHALL 把该会话标识**透传至编排器**（此前丢弃），使子任务轨迹按发起会话归属。

#### Scenario: CLI 直连内核
- **GIVEN** 用户以 CLI 模式启动
- **WHEN** 发起一次会话
- **THEN** 会话通过同一后端 API 层驱动内核 loop，行为与 Web 模式一致

#### Scenario: 会话标识透传至记忆沉淀
- **GIVEN** 用户在某会话（`session_id` 非空）内发起一轮对话
- **WHEN** 内核完成本轮并沉淀记忆
- **THEN** 沉淀条目的 `session_id` 等于该会话标识（API 层透传，不替换、不丢弃）

#### Scenario: 会话标识透传至编排子任务
- **GIVEN** 用户在某会话（`session_id` 非空）内经 `run_task` 派发一次编排任务
- **WHEN** 编排器把子任务交给子 Agent 执行
- **THEN** 执行携带该会话标识（不透传即丢弃是缺陷），子任务轨迹按该会话归属

#### Scenario: 会话记忆按会话读取
- **GIVEN** 存在分属两个会话的记忆条目
- **WHEN** 经 `get_memory(session_id)` 读取其中一个会话
- **THEN** 只返回归属于该会话的条目，其他会话与未归属条目不出现在结果中

#### Scenario: 会话压实
- **GIVEN** 某会话已积累多条 L2 episodic 条目
- **WHEN** 调用 `compact(session_id)`
- **THEN** 触发该会话的压实（存储层按会话聚合与归档语义生效），而非空操作

#### Scenario: 配置单一来源
- **GIVEN** 用户在任一模式配置了 LLM API
- **WHEN** 切换到另一模式
- **THEN** 该配置生效且无需重复配置

### Requirement: LLM API 可配置
系统 SHALL 支持在 Web 与桌面 UI 内配置 LLM provider、endpoint、API key、base URL 与**模型上下文窗口**
（`context_window`，用于派生 token 预算），并可配置执行循环的预算旋钮（`output_reserve`、
`max_rounds`）。保存 SHALL 把配置**写入后端配置源（config.yaml）并立即生效**：落盘 SHALL 原子提交
（不留下半写状态），运行中的执行循环 SHALL 立即取用新上限（无需重启或重建循环）。API key SHALL
以 `${VAR}` 引用形式保存与回显，**绝不**以明文写入配置文件、库、遥测或前端日志。

#### Scenario: UI 内配置 LLM API
- **GIVEN** 用户打开 Web 或桌面设置页
- **WHEN** 填写 provider/endpoint/key/base URL 并保存
- **THEN** 配置写入后端配置源并立即生效，密钥不进入前端日志

#### Scenario: 密钥安全存储
- **GIVEN** 用户保存了 API key
- **WHEN** 系统持久化配置
- **THEN** key 存储在本地受保护配置文件中，不入库、不进遥测

#### Scenario: 密钥持久化失败
- **GIVEN** 系统持久化 LLM API key 时发生磁盘写满或权限不足
- **WHEN** 保存配置失败
- **THEN** 回滚本次配置变更并提示用户，不留下半写状态，密钥不进入错误日志

#### Scenario: 上下文窗口与预算热生效
- **GIVEN** 系统已在运行，用户经 UI 保存 `context_window` 与预算旋钮
- **WHEN** 保存成功
- **THEN** 运行中的执行循环立即取用派生后的 token 预算与循环次数上限，下一次执行即按新上限判定

#### Scenario: 配置持久化后可重读
- **GIVEN** 用户经 UI 保存 `context_window` / `output_reserve` / `max_rounds`
- **WHEN** 重新加载配置（新进程 / 重新 `load()`）
- **THEN** 保存的值原样生效（非仅内存态），非法取值不落盘

### Requirement: CLI 友好交互
系统 SHALL 在 CLI 模式提供声明式、响应式的终端交互（折叠块、流式输出、多面板、焦点管理），复刻 Claude Code 式 Ink 体验。

实现：Textual（Python 原生）

流式增量 SHALL 以**结构化块为单位**固化：当尾段处于**未闭合的结构化块**内（Markdown 表格：表头行 / `|---|` 分隔行 / 数据行；或代码围栏）时，SHALL **延后**按行边界或字符阈值的固化，使该块作为**整体**落入**同一**渲染块（表格渲染为表格、围栏渲染为代码块），SHALL NOT 依行边界把它拆成多个独立块；仅当块**闭合**（出现空行或块外内容开始）后方恢复常规固化。未闭合块的缓冲 SHALL 有界（超硬上限时兜底固化，约束内存与重 wrap 代价）。

流式渲染 SHALL NOT 保证「每分片一次重绘」：增量 SHALL 允许**先入缓冲、按固定节拍合并渲染一次**（合帧节流），使渲染次数与分片速率**解耦**；处于**未闭合**状态的 Markdown 表格块 SHALL **延后渲染**（不在中间态逐行绘制），待块闭合或超出硬上限后**一次整块成型**。代码围栏分支 SHALL 维持**流式可见**（不延后）。所有挂起缓冲区 SHALL **有界**，且回复收尾（含异常 / 中断）时挂起尾段 SHALL 被最终固化（不丢字）。

**agent 回复的渲染格式 SHALL 与「回复从哪条入口进入时间线」无关**：续聊（`--session <id>`）把既有转录**铺入时间线**时，其中的 **agent 回复** SHALL 以**与实时流式路径同一**格式（Markdown）渲染 —— 既有回复中的代码围栏 / 表格 SHALL 同样渲染为代码块 / 表格，SHALL NOT 退化为**逐行明文**；**用户消息** SHALL 以既有 `❯` 回显行呈现（逐字转义）。续聊铺入 SHALL NOT 改写既有转录的**内容**（仅使**呈现格式**与实时路径对齐）；转录读取面与未登记会话的 fail-closed 校验 SHALL NOT 因此放宽。

「围栏渲染为代码块」SHALL 含**视觉可辨识**、不止于语法高亮：代码块 SHALL 以**与正文可辨识**的背景呈现 —— 该背景 SHALL **不透明**，且与 TUI 主背景的 **WCAG 相对亮度对比度 SHALL ≥ 2.0** ⇒ 块与正文**一眼可辨**（不依赖用户放大或选词）。深色主题下 SHALL NOT 以**近透明**的深色叠加充数（叠加后与主背景的明度差趋近于零，等同未渲染）。

CLI SHALL 以**单一真源**维护斜杠命令清单（命令名 / 参数 / 说明），命令浮层 SHALL 据此呈现；真源内的每条命令 SHALL 可由既有分发链**实际执行**（SHALL NOT 呈现「采纳后无反应」的命令）。输入以 `/` 起始时，CLI SHALL 呈现**命令浮层**（命令名 + 说明，按前缀收窄），SHALL 支持 `↑`/`↓` 移动高亮、`Tab` 采纳高亮项、`Esc` 收起；输入为高亮项**前缀**时 `Enter` SHALL 同样采纳。**采纳 SHALL 只改写输入框文本**（带参数命令补出参数位），SHALL NOT 提交。

浮层 SHALL 为**纯呈现层**：既有命令的**语义**与**分发次序** SHALL NOT 因其改变 —— 完整命令输入（如 `/main`）、未知前缀（如 `/zzz`）与普通消息 SHALL 仍走既有路径；`↑`/`↓`/`Tab`/`Esc` 的接管 SHALL **仅在浮层呈现期间**生效（收起时既有按键行为逐字不变）。对**参数可取枚举**的命令（如 `/focus <子任务标识>`），浮层 SHALL 呈现**二级**候选，其数据 SHALL 取自既有面（SHALL NOT 新建第二数据源）。**审批挂起期间** SHALL NOT 呈现浮层（y/n 决断输入 SHALL NOT 被遮蔽或改写）。输入框 SHALL 内联呈现**幽灵补全**（ghost text，与浮层候选同源），`→` SHALL 采纳。

#### Scenario: 流式输出
- **GIVEN** 内核产生分片回复
- **WHEN** CLI 收到分片
- **THEN** 终端增量渲染回复，不整块刷新

#### Scenario: 流式结构化块整体解析
- **GIVEN** 内核分片回复中含跨行的结构化块（Markdown 表格：表头行 / `|---|` 分隔行 / 数据行；或代码围栏）
- **WHEN** CLI 逐片收到该块
- **THEN** 该块作为**整体**落入**同一**渲染块（不依行边界或字符阈值把它拆成多个块），使表格渲染为表格、围栏渲染为代码块；块闭合（空行或块外内容开始）后方恢复常规固化

#### Scenario: 流式回显合帧与表格延后渲染
- **GIVEN** 内核以分片（SSE delta）方式回复，且分片可能**逐词**到达
- **WHEN** CLI 逐片收到回复
- **THEN** 渲染**不**保证每片一次重绘 —— 增量先入缓冲、按固定节拍（合帧）合并为一次渲染，使渲染次数与分片速率**解耦**；处于**未闭合**状态的 Markdown 表格块**延后渲染**（不在中间态逐行绘制），待块闭合或超出硬上限后**一次整块成型**；代码围栏分支维持**流式可见**（不延后）

#### Scenario: 续聊转录按同格式渲染（回复不退化为明文）
- **GIVEN** 一个已登记的会话，其既有转录中某条 **agent 回复**含 Markdown 代码围栏（或表格）
- **WHEN** 以 `--session <id>` 续聊，既有转录被铺入时间线
- **THEN** 该 agent 回复渲染为 **Markdown** 块（围栏渲染为**代码块**、表格渲染为**表格**），**与实时流式路径同格式**，SHALL NOT 为逐行明文；**AND** 其中的用户消息仍以 `❯` 回显行呈现

#### Scenario: 代码块与正文可辨识（深色主题下不成透明块）
- **GIVEN** 回复含一段代码围栏，TUI 处于**深色**主题
- **WHEN** 该围栏渲染为代码块
- **THEN** 该块的背景**不透明**、且与主背景的**对比度 ≥ 2.0** ⇒ 块与正文**一眼可辨**；**AND GIVEN** 默认的**近透明**深色叠加（合成为 `#101010`、对比度 ≈ 1.02）
- **THEN** **不**满足本条（该默认样式被本 Requirement 排除）

#### Scenario: 折叠块展示
- **GIVEN** 回复包含长输出或工具结果
- **WHEN** CLI 渲染该回复
- **THEN** 长内容默认折叠，用户可展开/收起

#### Scenario: 终端审批确认
- **GIVEN** 执行中某高风险工具调用被确认门要求人工审批
- **WHEN** TUI 弹出审批提示
- **THEN** 用户输入 y 批准 / n 拒绝后执行继续；输入其他值提示重输

#### Scenario: 斜杠唤起命令浮层并按前缀收窄
- **GIVEN** TUI 就绪、输入框为空
- **WHEN** 用户输入 `/`
- **THEN** 呈现命令浮层，列出**单一真源**内的**全部**命令（命令名 + 说明）；输入继续键入时候选**按前缀收窄**；无匹配前缀（如 `/zzz`）时浮层收起；`Esc` 收起

#### Scenario: 键盘移动高亮并采纳（只改写输入框、不提交）
- **GIVEN** 命令浮层呈现中，高亮落在某命令
- **WHEN** 用户按 `↑`/`↓` 移动高亮，按 `Tab`（或输入为高亮项**前缀**时按 `Enter`）采纳
- **THEN** 输入框文本被改写为该命令（**带参数**命令补出参数位），该输入**不被提交**；焦点仍留在输入框（`Tab` SHALL NOT 把焦点移走）

#### Scenario: 采纳不改变既有命令的语义与分发次序
- **GIVEN** 用户提交的是**完整**命令输入（如 `/main`）或**未知**前缀（如 `/zzz`）或普通消息
- **WHEN** 提交
- **THEN** 走**既有**路径（`/main` 切回主视图、`/zzz` 进普通对话、审批 y/n 语义不变），浮层 SHALL NOT 改变其命运；`/focus <标识>` 的**忙态豁免** SHALL NOT 受影响

#### Scenario: 二级参数候选取自既有面
- **GIVEN** 某命令的参数**可取枚举**（`/focus <子任务标识>`，标识集为**既有**在途子任务面）
- **WHEN** 用户输入命令名 + 空格（如 `/focus `）
- **THEN** 呈现**二级**候选（既有子任务标识），采纳后填入 `/focus <标识>`；SHALL NOT 新建第二数据源

#### Scenario: 审批挂起期间不呈现浮层
- **GIVEN** 某高风险工具调用正等待 y/n 审批（审批挂起中）
- **WHEN** 用户在输入框输入任意内容（含 `/` 起始）
- **THEN** SHALL NOT 呈现命令浮层（y/n 决断输入 SHALL NOT 被遮蔽或改写），审批语义逐字不变

#### Scenario: 命令幽灵补全与 `→` 采纳
- **GIVEN** 输入框内容为某命令名的**前缀**（如 `/re`）
- **WHEN** CLI 呈现该输入
- **THEN** 输入框内联显示剩余字符的**幽灵补全**（与浮层候选**同源**）；按 `→` 采纳该补全

### Requirement: TUI 子任务运行态与详情

TUI（REPL `/task`）SHALL 逐子任务呈现**标题**与**运行状态**（运行中 / 完成 / 失败 / 续跑跳过），并可展开查看该子任务的**详情**（里程碑事件 / 验收标准 / 判定理由 / 结果节选）。详情数据 SHALL 全部取自既有 `task.*` 事件载荷，SHALL NOT 新建第二数据源。

里程碑事件（`subtask_progress`，载荷已由编排层按内层类型白名单化）SHALL 被渲染为**用户可见**文本：工具类里程碑 SHALL 复用既有工具动作行的**友好名**呈现（SHALL NOT 暴露内部 `tool_id` 与原始参数），轮次级里程碑 SHALL 呈现轮次与成败。白名单**表外**的事件类型 SHALL NOT 产生任何呈现（不落空行、不落占位、不谎报里程碑）。

**进入子 agent 会话 / 主-子焦点切换** SHALL NOT 在本 Requirement 内：子 Agent 消息流**无数据源**（转录只注入主 loop），故本 Requirement 的「详情」仅指既有事件载荷内可见的字段。

#### Scenario: 子任务运行中可见状态徽标
- **GIVEN** 一个在途任务且其子任务已开工
- **WHEN** TUI 时间线呈现该子任务折叠块
- **THEN** 标题含**运行中**标记；该子任务收尾后标题落 ✓ / ✗（续跑跳过落「已完成（续跑跳过）」）

#### Scenario: 里程碑事件展开可见
- **GIVEN** 子任务执行中产生里程碑事件（`action_started` / `action_completed` / `step_completed`）
- **WHEN** 该子任务折叠块被展开
- **THEN** 依序可见各里程碑（工具类显示友好名与耗时，轮次级显示轮次与成败），且**不含**原始工具参数

#### Scenario: 表外事件不呈现
- **GIVEN** 编排层未外发某一事件类型（白名单表外类型按既有口径静默丢弃）
- **WHEN** TUI 呈现该子任务详情
- **THEN** 详情不出现该类型的内容（不落空行与占位，不谎报里程碑）

#### Scenario: 里程碑先于折叠块到达时静默忽略
- **GIVEN** 某 `subtask_progress` 事件的子任务标识**没有**对应折叠块（未收到其 `subtask_started`）
- **WHEN** TUI 处理该事件
- **THEN** 静默忽略（不新建折叠块、不抛裸异常、不影响其它子任务的详情）

### Requirement: TUI 子 Agent 焦点视图

TUI（REPL）SHALL 支持**主视图 ⇄ 子任务焦点视图**的切换：`/focus <子任务标识>` SHALL 进入该子任务的焦点视图，`/main` 或 `F2` SHALL 返回主视图。

焦点视图 SHALL 呈现该子任务的**标题 + 运行状态**（沿用既有折叠块口径 `⟳` / `✓` / `✗`）与**详情**（验收标准 / 里程碑 / 判定理由 / 结果节选），并随该子任务的里程碑与收尾事件**实时刷新**。

视图数据 SHALL 全部取自既有 `task.*` 事件载荷，SHALL NOT 新建第二数据源，SHALL NOT 接子 Agent 消息流（转录只注入主 loop）；里程碑 SHALL 沿用既有**友好名**呈现（SHALL NOT 暴露内部 `tool_id` 与原始参数）。

切回主视图 SHALL NOT 改变主时间线的**内容**（呈现层切换，非数据层变更）。未知子任务标识 SHALL NOT 切换视图（提示并保持主视图）。焦点命令 SHALL 在任务**运行中**可用（SHALL NOT 被忙态拒绝拦截）。`task_started` 与**审批挂起**时 SHALL 回到主视图。

#### Scenario: 聚焦显示子任务框且主时间线不可见
- **GIVEN** 一个在途任务且其子任务已开工（已有对应折叠块）
- **WHEN** 用户输入 `/focus <该子任务标识>`
- **THEN** 焦点面板可见且标题含该子任务标识与运行态徽标，主时间线不可见，且该输入**不**被送入推理

#### Scenario: 返回主视图后主时间线内容逐字不变
- **GIVEN** 已聚焦某子任务
- **WHEN** 用户输入 `/main` 或按 `F2`
- **THEN** 主时间线可见且其文本与聚焦前**逐字一致**（焦点视图不改主时间线内容）

#### Scenario: 聚焦期间随里程碑与收尾实时刷新
- **GIVEN** 已聚焦某在途子任务
- **WHEN** 该子任务产生里程碑事件（`action_started` / `action_completed` / `step_completed`）或收尾
- **THEN** 焦点面板正文依序补入里程碑（工具类显示友好名与耗时），收尾后标题落 ✓ / ✗ 且正文含判定理由

#### Scenario: 未知子任务标识不切换视图
- **GIVEN** 某标识**没有**对应折叠块（未收到其 `subtask_started`）
- **WHEN** 用户输入 `/focus <该标识>`
- **THEN** 不切换视图（主时间线仍可见），并给出未找到的提示

#### Scenario: 焦点命令在任务运行中可用
- **GIVEN** 一个在途任务（REPL 处于忙态，普通输入会被拒绝）
- **WHEN** 用户输入焦点命令（`/focus <标识>` 或 `/main` / `F2`）
- **THEN** 命令被处理（不被忙态拒绝），且**不**进入推理

#### Scenario: 焦点面板不泄露内部标识与原始参数
- **GIVEN** 已聚焦某子任务且其已产生工具类里程碑
- **WHEN** 焦点面板呈现里程碑
- **THEN** 面板文本含**友好名**（如 `Bash`），且**不含**内部 `tool_id` 与工具原始参数

### Requirement: Web 界面访问
系统 SHALL 支持以 HTTP 服务 + 单页应用（SPA）形式提供 Web 界面，流式输出通过 SSE 推送。
后端 SHALL 在 SPA 构建产物存在时将其挂载为站点根，并在**产物缺失时降级为纯 API 模式**（后端照常
可用，不因缺前端而启动失败）；静态挂载 SHALL NOT 遮蔽既有 REST/SSE 端点。

流式输出 SHALL 区分**增量帧**与**终态帧**：增量 SHALL 以**专类型**帧推送（载荷为增量文本），
终态结果 SHALL 以结果帧推送（载荷为完整结果）——两类帧 SHALL NOT 共用一个类型。前端消费增量帧
SHALL 以**文本追加**方式呈现（首帧新建、其后原地追加，终态帧收口），SHALL NOT 逐帧新建行，SHALL NOT
把载荷序列化为 JSON 文本展示。

实现：Svelte SPA

#### Scenario: 浏览器访问
- **GIVEN** 用户启动 Web 模式
- **WHEN** 浏览器打开服务地址
- **THEN** 加载 SPA，可发起会话并实时看到流式回复

#### Scenario: 增量帧以文本追加（非逐帧 JSON）
- **GIVEN** Web 会话正在流式生成回复，后端逐段推送增量帧
- **WHEN** 前端消费这些增量帧
- **THEN** 增量文本**追加**到同一条回复中（不逐帧新建行、不逐帧渲染 JSON 载荷），终态帧收口为完整回复

#### Scenario: SSE 断线重连
- **GIVEN** Web 会话的 SSE 流式连接因网络抖动或服务端重启而断开
- **WHEN** 连接中断
- **THEN** 客户端按指数退避自动重连并恢复流式推送，期间以心跳探测连接存活，避免流式输出卡死

#### Scenario: 未构建前端时降级为纯 API
- **GIVEN** 后端以 `serve` 启动，而 SPA 构建产物不存在
- **WHEN** 服务就绪
- **THEN** 服务照常启动，REST/SSE 端点全部可达（不因缺前端而失败）

#### Scenario: 静态挂载不遮蔽端点
- **GIVEN** SPA 构建产物已挂载为站点根
- **WHEN** 客户端请求既有 REST 端点（如 `GET /llm-config`）
- **THEN** 返回该端点的 JSON 响应，不被静态文件兜底吞掉

### Requirement: 桌面打包
系统 SHALL 支持将桌面端打包为可执行安装文件（Windows / macOS / Linux），并内置拉起本地后端的能力。
桌面壳 SHALL 复用与 Web 相同的 SPA 构建产物，且 sidecar 拉起 SHALL 由 `DesktopBridge` 实现
（spawn 本地后端进程），壳仅负责开窗口 / 挂 SPA / 启 sidecar。

实现：Tauri 壳 + sidecar

#### Scenario: 安装包运行
- **GIVEN** 用户安装桌面安装包
- **WHEN** 启动应用
- **THEN** 桌面壳自动拉起本地后端，加载同一 SPA 并可正常会话

#### Scenario: sidecar 拉起
- **GIVEN** 桌面入口启动
- **WHEN** 调用 sidecar 拉起
- **THEN** 以本地后端进程形式 spawn（不经 shell 解释执行、参数逐项传递），失败以结构化错误报告而非静默成功

### Requirement: Web 与桌面体验一致
系统 SHALL 使桌面端复用与 Web 相同的 SPA 构建产物，保证二者体验 100% 一致。

#### Scenario: 界面一致性
- **GIVEN** 同一版本的 Web 与桌面端
- **WHEN** 打开同一功能页面
- **THEN** 二者界面与交互完全一致

### Requirement: 多模态输入
系统 SHALL 支持图像与语音等多模态输入的接入，并统一路由到具备对应能力的模型处理。

#### Scenario: 图像输入理解
- **GIVEN** 用户在 UI 中附加图片（截图/照片）
- **WHEN** 发起会话
- **THEN** 图片经统一输入管道交给具备视觉能力的模型理解，结果并入上下文

#### Scenario: 语音输入转写
- **GIVEN** 用户以语音方式输入
- **WHEN** 语音被采集
- **THEN** 系统先转写为文本再进入统一内核，必要时保留原始音频引用

#### Scenario: 模态能力缺失降级
- **GIVEN** 当前配置的模型不具备某模态理解能力
- **WHEN** 用户提交该模态输入
- **THEN** 系统明确提示不支持并给出可替换建议，不静默丢弃输入

### Requirement: 实时语音输出
系统 SHALL 支持将内核生成的文本回复以流式 TTS 合成语音实时播报，允许用户在播报过程中打断（barge-in），并保留语音与文本会话上下文的双向引用。

#### Scenario: 流式 TTS 播报
- **GIVEN** 内核产生分片文本回复
- **WHEN** 用户开启了语音播报
- **THEN** 分片文本被增量送入 TTS 合成并连续播报，不等待整段回复完成

#### Scenario: 用户打断（barge-in）
- **GIVEN** 语音播报正在进行
- **WHEN** 用户开口说话或按下打断键
- **THEN** 系统立即停止当前播报并转入语音输入处理，被打断的文本不丢失并保留在会话记录中

#### Scenario: 语音上下文引用
- **GIVEN** 会话中既有语音输入又有语音播报
- **WHEN** 用户后续引用或追问先前内容
- **THEN** 语音与文本共享同一会话记录可相互引用，必要时保留原始音频引用

### Requirement: Web Client 分离
系统 SHALL 支持 Web 前端作为纯静态资源独立托管，与常驻 Harness Host 后端解耦部署：前端经统一后端 API 连接 Host，前端升级不要求后端重启。

#### Scenario: 纯静态独立托管
- **GIVEN** Web SPA 构建产物
- **WHEN** 部署到任意静态托管
- **THEN** 前端可加载并连接常驻 Harness Host 后端 API 正常会话

#### Scenario: 前后端解耦升级
- **GIVEN** Web Client 与 Host 后端独立部署
- **WHEN** 前端发布新版本
- **THEN** 前端可独立升级，无需重启 Host 后端（后端 API 兼容时）

### Requirement: 会话注册表持久化与跨入口共享
统一后端 API 层 SHALL 将对话会话标识登记于**跨进程共享的持久注册表**（落 `$CORE_STATE_DIR` 下 JSON 快照），使 CLI / Web / Desktop 三种入口（含各自独立进程）对会话标识的**创建与校验共享同一事实来源**。注册表 SHALL 采用**读透 + 写时合并**语义：校验（`exists`）与枚举（`list`）每次读回磁盘，创建（`create`）先读回磁盘再合并写回 —— 以支持「长驻 `serve` 进程看到另一进程（CLI）新建的会话」；创建 SHALL 以**进程内互斥**保护，使**同进程多线程**并发创建不相互覆盖。**跨进程**同刻并发创建 SHALL NOT 被声称受保护（进程内互斥不跨进程，属已知局限，不得据此断言跨进程安全）。

注册表持久化 SHALL NOT 放宽会话校验：未登记于注册表的 `session_id` SHALL 仍被拒绝（`UI_SESSION_NOT_FOUND`）。注册表为**派生状态**，其文件缺失或损坏 SHALL 使系统以空注册表启动，SHALL NOT 阻断启动。

后端 API 层 SHALL 提供**会话枚举**能力（HTTP `GET /sessions`），返回注册表内全部对话会话（标识 + 模式），三入口所见一致。

注：本 Requirement 与「三模统一内核启动」正交 —— 后者约束 `session_id` 的**值语义**（生成后无改写透传至循环与记忆写入），本 Requirement 约束会话标识的**持久化与跨入口可见性**。

#### Scenario: 跨进程会话可见
- **GIVEN** CLI 进程经 `create_session` 建立了一个会话
- **WHEN** 另一进程（如 `serve` 或另一次 CLI 调用）以该 `session_id` 发起 `run_loop` / 读记忆
- **THEN** 该会话被认作有效，不再返回 `UI_SESSION_NOT_FOUND`

#### Scenario: 会话枚举端点
- **GIVEN** 注册表内已有若干对话会话
- **WHEN** 经后端 API（`GET /sessions`）枚举会话
- **THEN** 返回注册表内全部对话会话（标识 + 模式，含创建时间），跨入口一致

#### Scenario: 未登记标识仍拒绝
- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 经后端 API 发起会话操作
- **THEN** 返回 `UI_SESSION_NOT_FOUND`（fail-closed，不放宽既有校验）

### Requirement: 会话转录的读取面

后端 API 层 SHALL 提供会话转录的读取面：HTTP `GET /session/{session_id}/messages` 返回该会话的
对话转录（按追加次序）。**未登记于注册表**的会话标识 SHALL 仍被拒绝（`UI_SESSION_NOT_FOUND`），
转录的读取面 SHALL NOT 放宽既有会话校验。

会话枚举（`GET /sessions`）的条目 SHALL 附**从转录派生**的 `title`（该会话**首条用户消息**截断；
该会话无用户消息 ⇒ 空串，SHALL NOT 以任何内容顶替）与 `updated_at`（最近一条转录的时间戳；
该会话无转录 ⇒ 回落注册表 `created_at`）：派生值 SHALL NOT 写入会话注册表（注册表只承载标识与
模式，不承载内容；避免第二真源）。**未注入转录存储**时（如库层直调 / 测试替身），枚举条目 SHALL
保持既有形状（只增不减 ⇒ 既有消费方不受影响）。

#### Scenario: 读取本会话转录

- **GIVEN** 一个已登记的会话，且其转录已有若干轮
- **WHEN** 经 HTTP `GET /session/{session_id}/messages` 读取
- **THEN** 按追加次序返回该会话的对话转录

#### Scenario: 未登记标识仍拒绝

- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 请求该会话的转录
- **THEN** 返回 `UI_SESSION_NOT_FOUND`（fail-closed，不放宽既有校验）

#### Scenario: 会话枚举附派生标题与最近活跃

- **GIVEN** 注册表内已有若干会话，其中某会话的转录含用户消息
- **WHEN** 经 HTTP `GET /sessions` 枚举
- **THEN** 该会话条目附 `title`（其首条用户消息截断）与 `updated_at`；
  无用户消息的会话 `title` 为空串（SHALL NOT 伪造出标题），`updated_at` 回落其 `created_at`

#### Scenario: 转录缺席时枚举形状不变

- **GIVEN** 未注入转录存储
- **WHEN** 经 HTTP `GET /sessions` 枚举
- **THEN** 条目保持既有形状（标识 + 模式 + 创建时间），不新增派生字段

### Requirement: Web 会话列表与切换

Web SPA SHALL 呈现**会话列表**（数据取自 `GET /sessions`），条目 SHALL 展示该会话的**派生标题**
（该会话无用户消息 ⇒ 以占位呈现，SHALL NOT 伪造标题）与**最近活跃**时间，并按最近活跃**降序**排列
（排序属呈现层，SHALL NOT 要求后端改变响应形状）。SPA SHALL 支持**点选**某会话以查看其对话转录
（`GET /session/{session_id}/messages`，按追加次序渲染）并**继续对话**（后续轮次归属该会话）。

SPA SHALL 提供**显式**新建会话入口。未选中会话时 SHALL NOT 以首条消息**隐式**创建会话（避免在列表
留下无对话的空会话），而 SHALL 提示用户先新建或选择会话。切换会话时，界面 SHALL NOT 把上一会话的
消息混入当前会话的呈现（呈现隔离）。

#### Scenario: 会话列表呈现

- **GIVEN** 已存在若干会话，其中部分有对话记录
- **WHEN** 打开 Web 界面
- **THEN** 呈现会话列表，条目含派生标题与最近活跃时间，按最近活跃降序排列

#### Scenario: 切换会话查看记录并继续对话

- **GIVEN** 界面上存在两个各有对话记录的会话
- **WHEN** 点选其中一个会话
- **THEN** 按追加次序渲染该会话的转录；随后发送的消息归属该会话，不出现另一会话的内容

#### Scenario: 显式新建会话

- **GIVEN** 用户打开 Web 界面且尚未选中任何会话
- **WHEN** 未新建会话即发送消息
- **THEN** 提示先新建或选择会话（不隐式创建会话）；点击「新建会话」后列表出现该新会话并可开始对话

### Requirement: 任务编排的 HTTP 面与 Web 任务区

统一后端 API 层 SHALL 经 HTTP `POST /task`（请求含会话标识与目标）以 **SSE** 流式返回编排任务的
`task.*` 进度事件，与 TUI `/task`、CLI `task` 走**同一编排器与同一事件面**（SHALL NOT 另造事件面）。
未登记于注册表的会话标识 SHALL 仍被拒绝（`UI_SESSION_NOT_FOUND`）；编排器未注入 SHALL 以结构化错误
（`UI_ORCHESTRATOR_UNSET`）经**错误帧**报告，SHALL NOT 向客户端抛裸异常或静默成功。

SPA SHALL 提供**任务区**，与会话列表**同处右栏位置而各自独立**：任务是**在途**运行态、会话是**持久**
记录，二者 SHALL NOT 合并为同一列表。任务区 SHALL 逐子任务呈现**标题**与**状态**（待执行 / 运行中 /
完成 / 失败），并可展开查看该子任务**详情**（里程碑 / 验收理由 / 失败理由，取自既有事件载荷）；
SHALL NOT 为此新建第二数据源。

任务收尾（`task_finished` / `task_failed`）SHALL 使该任务**移出在途列表**（任务区回落），SHALL NOT
因收尾而进入会话列表（任务不产生会话）。

**进入子 agent 会话 / 主-子焦点切换** SHALL NOT 在本 Requirement 内：子 Agent 消息流**无数据源**
（转录只注入主 loop），故本 Requirement 的「详情」仅指既有事件载荷内可见的字段。

#### Scenario: HTTP 派发任务并流式呈现进度

- **GIVEN** 一个已登记的会话与一个可用编排器
- **WHEN** 经 HTTP `POST /task` 派发一个目标
- **THEN** 以 SSE 依序流式返回该任务的 `task.*` 进度事件（含子任务开始 / 运行态回流 / 收尾），与 TUI `/task` 所见的同一事件面

#### Scenario: 未登记会话标识被拒绝

- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 经 HTTP `POST /task` 派发任务
- **THEN** 返回 `UI_SESSION_NOT_FOUND` 错误帧（fail-closed，不放宽既有会话校验）

#### Scenario: 编排器未注入时报结构化错误

- **GIVEN** 后端未注入编排器
- **WHEN** 经 HTTP `POST /task` 派发任务
- **THEN** 返回 `UI_ORCHESTRATOR_UNSET` 错误帧（不裸抛、不静默成功）

#### Scenario: 任务区与会话列表并列不混池

- **GIVEN** 界面上既有若干持久会话，又有在途任务
- **WHEN** 打开 Web 界面
- **THEN** 右栏同时呈现任务区与会话列表两个独立区块；任务**不出现**在会话列表中，会话**不出现**在任务区中

#### Scenario: 子任务标题与状态可见、详情可展开

- **GIVEN** 一个在途任务且其子任务已开始执行
- **WHEN** 任务区呈现该任务
- **THEN** 逐子任务显示标题与状态（待执行 / 运行中 / 完成 / 失败），展开可见该子任务的里程碑或验收 / 失败理由

#### Scenario: 任务收尾后回落

- **GIVEN** 一个在途任务
- **WHEN** 该任务收尾（`task_finished` / `task_failed`）
- **THEN** 该任务移出任务区的在途列表（任务区回落），且**不**出现在会话列表中

### Requirement: 思考过程回显（Think）
系统 SHALL 在**三端**（TUI / Web / APP）以**折叠块**呈现模型的思考原文（`loop.reasoning` 事件），用户可展开查看全文；同一轮的思考增量 SHALL **归并到同一个折叠块**（增量更新，SHALL NOT 逐段新建块）。思考原文 SHALL ONLY 经该事件面呈现，SHALL NOT 写入转录 / 记忆 / 日志 / trace 遥测（思考回显是**纯呈现层**）。

折叠的**缺省形态**分端：**TUI** SHALL 缺省呈现为**步骤块的缩略态**（正文可见、只呈现**末尾有界行数**，超出部分折叠），其标题口径、三态与手势 SHALL 遵循「TUI 步骤块（缩略 / 全文 / 收起）」Requirement（SHALL NOT 在本条内另立一份口径）；**Web / APP** SHALL 缺省**收起**（承既有形态，逐字不变）。

**未开启**思考回显时（`llm.show_thinking` 缺省 `false`）系统 SHALL NOT 产出该事件、三端呈现 SHALL NOT 出现思考块，事件面与既有缺省**逐字一致**。Web / APP 端 SHALL 复用既有 SSE 事件通道呈现（SHALL NOT 新建端点、SHALL NOT 新建第二数据源）；APP 复用与 Web 相同的 SPA 产物。

#### Scenario: TUI 思考折叠回显
- **GIVEN** 思考回显已开启，且模型逐段返回思考原文
- **WHEN** TUI 消费 `loop.reasoning` 事件
- **THEN** 思考文本落入**单个**步骤块（缺省为**缩略态**：正文可见、只呈现末尾有界行数），随增量**实时**持续更新且可展开查看全文；同一轮的主回复呈现（流式增量与终态收口）**不受影响**

#### Scenario: Web 思考折叠回显
- **GIVEN** 思考回显已开启，Web 会话正在流式产出思考原文
- **WHEN** 前端消费 `loop.reasoning` 帧
- **THEN** 思考文本落入**单个**缺省收起的折叠块（`details` 式），增量**追加**到同一块（不逐段新建、不渲染 JSON 载荷），终态帧不改写该块

#### Scenario: 未开启思考回显时三端不呈现
- **GIVEN** 思考回显未开启（缺省），且模型响应携思考原文
- **WHEN** 一轮对话在三端任一端结束
- **THEN** 事件面**不产** `loop.reasoning`，三端呈现中**不出现**思考块，输出与既有缺省**逐字一致**

### Requirement: TUI 会话切换（`/resume`）

TUI SHALL 提供 `/resume <会话标识>` 斜杠命令，把交互会话**切换到既有会话**并**还原其内容**：时间线
SHALL 被清空并以目标会话的既有转录**重新铺入**（agent 回复 SHALL 以与实时流式路径**同一**的 Markdown
格式呈现 —— 承「CLI 友好交互」，SHALL NOT 退化为逐行明文；用户消息 SHALL 以 `❯` 回显行呈现）。
切换后**后续轮次** SHALL 落在**目标**会话（`run_loop` / `run_task` SHALL 以新标识调用）。

会话候选取**既有**面（`UIAPILayer.list_sessions()`，SHALL NOT 新建第二数据源），其二级清单 SHALL 由
「CLI 友好交互」的命令浮层呈现；浮层采纳 SHALL 仍**只改写输入框**（`/resume <标识>`）、SHALL NOT 提交。

切换 SHALL **fail-closed 且先验证后落地**：目标会话**未登记**（`session_messages` 拒绝）⇒ SHALL NOT
改动当前会话的**任何**状态（时间线 / 会话标识 / 呈现态**逐字不变**），仅落一行错误。`/resume`
**无参数**（或参数为空）⇒ SHALL 只提示用法、SHALL NOT 切换。

切换 SHALL **仅在本轮执行结束之后**发生（忙碌中 SHALL 拒绝并提示等待，SHALL NOT 与在途轮次并发
改写会话状态）。切换 SHALL 复位**跨会话无意义**的呈现态（子任务折叠块 / 子 Agent 焦点视图 / 动作块 /
思考块 / 流式缓冲），SHALL NOT 残留上一会话的句柄或缓冲。

#### Scenario: 切换会话并还原其内容
- **GIVEN** 当前会话 A，且存在既有会话 B（已登记，其转录含用户消息与含代码围栏的 agent 回复）
- **WHEN** 用户提交 `/resume <B>`
- **THEN** 时间线被清空并铺入 **B** 的既有转录：B 的 agent 回复渲染为 **Markdown**（围栏成代码块）、
  用户消息以 `❯` 回显行呈现
- **AND THEN** 切换后的**后续轮次**落在 **B**（`run_loop` / `run_task` 收到标识 `<B>`）

#### Scenario: 未登记会话 fail-closed（当前会话逐字不变）
- **GIVEN** 当前会话 A、时间线已有内容
- **WHEN** 用户提交 `/resume <未登记标识>`
- **THEN** **不切换**：时间线内容、当前会话标识与呈现态**逐字不变**，仅落一行错误

#### Scenario: `/resume` 无参数只提示用法
- **GIVEN** TUI 就绪
- **WHEN** 用户提交 `/resume`
- **THEN** 只提示用法、SHALL NOT 切换会话、SHALL NOT 改动时间线

#### Scenario: 本轮执行期间拒绝切换
- **GIVEN** 一轮执行**尚未结束**（忙碌）
- **WHEN** 用户提交 `/resume <已登记标识>`
- **THEN** 拒绝切换（提示处理中）、当前会话与时间线**逐字不变**

### Requirement: 可选 Web 依赖测试守卫
Web 能力的测试文件（如 `tests/test_serve.py`）对可选依赖（fastapi/starlette 等）的模块级导入 MUST 位于 `pytest.importorskip` 守卫之后；守卫 SHALL 作为文件首个导入动作执行。在未安装 Web 可选依赖的环境中，测试文件 SHALL 整体优雅 skip，不产生 collection error。

#### Scenario: 缺依赖环境优雅跳过
- **GIVEN** 测试环境未安装 fastapi/starlette 可选依赖
- **WHEN** 运行 pytest 收集 `tests/test_serve.py`
- **THEN** 该文件所有测试标记为 skipped，无 collection error，其他测试文件的执行不受影响

#### Scenario: 有依赖环境行为不变
- **GIVEN** 测试环境已安装 fastapi/starlette
- **WHEN** 运行 pytest 收集 `tests/test_serve.py`
- **THEN** 全部测试正常收集与执行，行为与守卫调整前一致

#### Scenario: 新增可选依赖导入的守卫合规
- **GIVEN** 后续向 Web 测试文件新增可选依赖的模块级导入
- **WHEN** 审查该导入位置
- **THEN** 该导入位于 `importorskip` 守卫之后（可带 `# noqa: E402`），不得先于守卫裸导入

### Requirement: TUI 只读诊断命令

TUI SHALL 提供一组**只读**斜杠命令（`/doctor` / `/status` / `/sessions` / `/config` / `/mcp` / `/skill` /
`/notes`），并把结果**就地**呈现为时间线上的一条结果块。命令名、说明与处理器的对应关系 SHALL 取自命令
登记的**单一真源**（SHALL NOT 与分发各记一份）。

结果 SHALL 来自与 CLI `doctor` / `status` **同一**的只读诊断源（SHALL NOT 各写一份检查逻辑），
并 SHALL NOT 含任何**密钥值**：涉及密钥的项 SHALL ONLY 呈现 `${VAR}` **引用名**与「可解析 / 不可解析」
的**布尔结论**；`/mcp` SHALL NOT 呈现端点 `args`。

只读命令 SHALL **零副作用**：SHALL NOT 追加对话轮次（`run_loop` / `run_task` SHALL NOT 被调用）、
SHALL NOT 写转录 / 记忆 / 笔记、SHALL NOT 改动呈现态（会话标识、时间线内容、子任务折叠块、焦点视图
**逐字不变**）；SHALL NOT 产生用户输入回显（`❯` 前缀行）。

只读命令 SHALL **不豁免忙态**：本轮执行尚未结束时提交 SHALL 被拒绝并提示等待（与 `/resume` 同侧）。

只读命令 SHALL NOT 接受参数（真源中其参数位为空）：带参数提交 SHALL ONLY 提示、SHALL NOT 执行。
真源**未登记**的斜杠输入 SHALL 保持既有行为（作为普通消息进入对话）；既有 6 条命令的语义、提示串与
分发次序 SHALL NOT 改变。

#### Scenario: 浮层列出只读命令并可采纳

- **GIVEN** TUI 就绪
- **WHEN** 用户输入 `/`
- **THEN** 浮层候选包含全部只读命令（顺序即真源顺序）
- **AND THEN** 采纳（`Tab` / `Enter`）SHALL ONLY 改写输入框（无参数位）、SHALL NOT 提交

#### Scenario: 执行命令落结果块且不进对话

- **GIVEN** TUI 就绪且诊断源已接线
- **WHEN** 用户提交 `/doctor`（或 `/status` / `/sessions` / `/config` / `/mcp` / `/skill` / `/notes`）
- **THEN** 时间线新增该命令的一条结果块
- **AND THEN** **无** `❯` 回显行、**无**对话轮次（`run_loop` / `run_task` SHALL NOT 被调用）

#### Scenario: 只读命令零副作用

- **GIVEN** 时间线已有内容、当前会话已登记、记忆与笔记已有若干条目
- **WHEN** 用户提交任一已登记只读命令
- **THEN** 会话标识、转录条数、记忆条目与笔记内容**逐字不变**；时间线除新增结果块外**逐字不变**

#### Scenario: 本轮执行期间拒绝只读命令

- **GIVEN** 一轮执行尚未结束（忙碌）
- **WHEN** 用户提交 `/doctor`
- **THEN** 拒绝执行（提示处理中），时间线**逐字不变**

#### Scenario: 只读输出不含密钥值

- **GIVEN** 配置中的密钥引用可解析（其值存在于环境或 keychain）
- **WHEN** 用户提交 `/config` 或 `/doctor`
- **THEN** 结果块只出现 `${VAR}` 引用名与「可解析」结论，**不出现**其解析结果

#### Scenario: 带参数与未登记前缀走既有路径

- **GIVEN** TUI 就绪
- **WHEN** 用户提交 `/doctor 额外参数` 或 `/zzz`
- **THEN** 前者 ONLY 提示（不执行、不改动呈现态）；后者仍作为普通消息进入对话（既有行为不变）


### Requirement: TUI 步骤块（缩略 / 全文 / 收起）

TUI 的**思考块**与**工具动作块** SHALL 统一为**步骤块**，其缺省形态为**缩略**（不是收起）：正文**可见**，但只呈现**末尾有界行数**（`N` 行），未呈现的部分以一行提示给出**剩余行数**。这样「Agent 正在干什么」在缺省视图下即可见（逐行滚动的原始执行信息），又不会让一则长输出淹没时间线。

**标题**：工具动作块的标题 SHALL 为工具的**友好名** + **有界目标摘要**（如 `⏺ Read  src/core/ui/repl.py`）。目标摘要 SHALL ONLY 取自**白名单的**结构性字段（`path` / `url` / `script` / `gate` / `pointer`），SHALL 为**单行**且有**有界长度**（超长以省略号收尾）；SHALL NOT 呈现**完整原始参数** —— 正文类参数（`content` / `old_content` / `new_content` 等）与内部 `tool_id` SHALL NOT 出现在标题中。目标摘要 SHALL 取自**既有**动作事件载荷（SHALL NOT 新建第二数据源）；取不到目标时标题 SHALL 只呈现友好名（不落占位、不谎报）。

**三态与手势**：

- **缩略态**（缺省）：正文 = **末尾有界行数** + 剩余行数提示；
- **全文态**：正文 = 全量；
- **收起态**：正文隐藏（仅标题可见）。

点**正文** SHALL 在**缩略 ⇄ 全文**之间切换；点**标题** SHALL 在**收起 ⇄ 展开**之间切换。无剩余行（正文未超有界行数）时 SHALL NOT 渲染展开入口（避免「点了没变化」）。

**折行**：步骤块正文 SHALL 以**确定宽度**呈现，超出面板宽度的行 SHALL **折行**完整可见（SHALL NOT 因宽度自适应而被裁掉）。

本条 SHALL NOT 覆盖**子任务折叠块**与**子 Agent 焦点视图**（后者另有 Requirement）：二者的既有口径逐字不变。缩略窗口 SHALL 恒跟随最新（SHALL NOT 因用户手动上滚而冻结）。

#### Scenario: 缩略窗口与剩余行数提示
- **GIVEN** 某步骤块正文超过有界行数（如工具输出 20 行）
- **WHEN** TUI 渲染该步骤块（未经用户展开）
- **THEN** 正文只呈现**末尾**有界行数，并有一行提示给出**未呈现的行数**与展开入口

#### Scenario: 点正文展开全文并回缩
- **GIVEN** 某步骤块处于**缩略态**且正文尚有未呈现的行
- **WHEN** 用户点击该块**正文**
- **THEN** 正文改为**全文**（未呈现的行一并呈现）；**再次**点击正文 ⇒ 回到**缩略态**（末尾有界行数）

#### Scenario: 点标题收起与展开
- **GIVEN** 某步骤块已展开（缩略态或全文态）
- **WHEN** 用户点击其**标题**
- **THEN** 该块**收起**（正文隐藏、仅标题可见）；**再次**点击标题 ⇒ 回到展开（缺省为缩略态）

#### Scenario: 标题带目标且不含正文参数
- **GIVEN** 一次工具动作的载荷含参数（如 `file_read` 的 `path`、`code_run` 的 `script`，或 `file_write` 的 `content`）
- **WHEN** TUI 渲染该动作的步骤块标题
- **THEN** 标题含**友好名**与该工具的**目标摘要**（白名单结构性字段；单行、有界长度）
- **AND** 标题**不含**完整原始参数 —— 内部 `tool_id`（`tools.*`）与 `content` / `old_content` / `new_content` 等正文参数均不出现

#### Scenario: 超宽正文折行而非裁切
- **GIVEN** 步骤块正文含**远超面板宽度**的单行（长路径 / 长命令 / 长 JSON）
- **WHEN** TUI 渲染该正文
- **THEN** 该行按面板宽度**折行**完整呈现，SHALL NOT 把超宽部分裁掉

#### Scenario: 思考增量实时追加且同轮归并同一块
- **GIVEN** 思考回显已开启，同一轮模型逐段返回思考原文
- **WHEN** TUI 逐条消费 `loop.reasoning` 事件
- **THEN** 增量**追加**到该轮的**同一个**步骤块（不逐段新建块），且随增量**实时**刷新（缩略态下亦即时反映最新末尾行）

