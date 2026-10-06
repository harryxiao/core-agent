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

#### Scenario: 流式输出
- **GIVEN** 内核产生分片回复
- **WHEN** CLI 收到分片
- **THEN** 终端增量渲染回复，不整块刷新

#### Scenario: 折叠块展示
- **GIVEN** 回复包含长输出或工具结果
- **WHEN** CLI 渲染该回复
- **THEN** 长内容默认折叠，用户可展开/收起

#### Scenario: 终端审批确认
- **GIVEN** 执行中某高风险工具调用被确认门要求人工审批
- **WHEN** TUI 弹出审批提示
- **THEN** 用户输入 y 批准 / n 拒绝后执行继续；输入其他值提示重输

### Requirement: Web 界面访问
系统 SHALL 支持以 HTTP 服务 + 单页应用（SPA）形式提供 Web 界面，流式输出通过 SSE 推送。
后端 SHALL 在 SPA 构建产物存在时将其挂载为站点根，并在**产物缺失时降级为纯 API 模式**（后端照常
可用，不因缺前端而启动失败）；静态挂载 SHALL NOT 遮蔽既有 REST/SSE 端点。

实现：Svelte SPA

#### Scenario: 浏览器访问
- **GIVEN** 用户启动 Web 模式
- **WHEN** 浏览器打开服务地址
- **THEN** 加载 SPA，可发起会话并实时看到流式回复

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
