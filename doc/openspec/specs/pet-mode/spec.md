# Pet Mode Specification

## Purpose

宠物模式（pet-mode）为 core-agent 提供后台自治循环扩展与宿主层三入口交互面：以统一 pet session 生命周期承载重复简单任务（信息收集 / 闲逛探索）、偏好追踪、定期反馈/惊喜，低优先级让行不阻塞主循环，三入口（/pet 斜杠命令、pet <verb> CLI argv、WebUI 自然语言）激活后台宠物会话，相当于"人类养宠物"——做当前不太重要的事、了解主人偏好、制造惊喜。

## Requirements

### Requirement: Background Pet Session Lifecycle
系统 SHALL 管理宠物会话的启动、休眠、恢复、异常退避、终止全生命周期，每次唤醒复用 `Loop.run()` 同步薄壳（asyncio.run 桥接）逐次执行，异常退避不残留半运行状态。

唤醒 SHALL **消费一个已派发任务**（队首先出队再执行，任务一次性）；**队列清空 ⇒ 会话进入休眠**（置让行态，复用既有 `SUSPENDED` 语义，**不新增状态枚举**，且 SHALL NOT 编造任务）；**新任务派发 ⇒ 自动唤醒**（清让行态）。休眠/让行中收到唤醒 SHALL 以 `PET_YIELDING` 拒绝（宿主驱动按既有预期态跳过，不空转、不刷屏）。

唤醒执行抛出的异常 SHALL 使会话转入 `BACKOFF` 并记录故障原因，且 SHALL **重新抛给宿主驱动**（驱动按 `FAILED` 记录、不中断其余宠物）—— SHALL NOT 静默吞掉。`BACKOFF` 会话 SHALL 可经控制面 `wake` 恢复为 `ACTIVE`（清故障），恢复后 SHALL 可继续派发与唤醒；失败任务 SHALL NOT 自动回队（是否重派由主人/控制面决定）。

#### Scenario: 启动与唤醒
- **GIVEN** 通过任一入口激活宠物会话
- **WHEN** 宠物会话启动 / 每次唤醒
- **THEN** 经 `Loop.run()` 同步薄壳执行一次自治任务，会话状态一致

#### Scenario: 任务执行后出队
- **GIVEN** 宠物队列中有若干已派发任务
- **WHEN** 宠物被唤醒执行
- **THEN** 队首任务被消费（出队）、交付真实 loop 执行，队列不再包含该任务

#### Scenario: 空闲自主入睡
- **GIVEN** 宠物队列中最后一个任务执行完毕（队列清空）
- **WHEN** 收尾
- **THEN** 会话进入休眠（让行态），**不编造新任务**，后续唤醒以 `PET_YIELDING` 拒绝

#### Scenario: 新任务自动唤醒
- **GIVEN** 宠物处于休眠（让行态）
- **WHEN** 主人派发新任务
- **THEN** 清让行态、自动唤醒，下次唤醒消费该新任务

#### Scenario: 休眠与恢复
- **GIVEN** 宠物会话处于让行或低优先级等待中
- **WHEN** 主循环释放资源
- **THEN** 宠物会话从休眠/让行态恢复，继续待办任务

#### Scenario: 异常退避
- **GIVEN** 宠物会话执行过程中出错
- **WHEN** 异常退避
- **THEN** 会话标记故障态、隔离，不残留半运行状态，不阻塞主循环

#### Scenario: 终止释放
- **GIVEN** 一个运行中的宠物会话
- **WHEN** 终止
- **THEN** 其任务与资源释放，无悬空引用

#### Scenario: 唤醒异常退避与恢复
- **GIVEN** 一只 `ACTIVE` 宠物且队列有待办任务
- **WHEN** 唤醒执行时 loop 抛出异常
- **THEN** 会话转入 `BACKOFF` 且故障原因可查，异常上抛给宿主驱动；控制面 `wake` 后恢复为 `ACTIVE`、故障清空，随后唤醒照常执行

### Requirement: Pet Task Types
系统 SHALL 支持重复简单任务作为宠物会话的可分配任务类型：信息收集（information gathering）、闲逛探索（idle exploration）。

#### Scenario: 信息收集任务
- **GIVEN** 宠物会话运行中
- **WHEN** 分配信息收集任务
- **THEN** 宠物按低优先级在后台收集信息，不阻塞主循环

#### Scenario: 闲逛探索任务
- **GIVEN** 宠物会话运行中
- **WHEN** 分配闲逛探索任务
- **THEN** 宠物在后台自主探索，结果进入会话上下文

### Requirement: Low-Priority Yielding
系统 SHALL 保证宠物低优先级让行：同步 + 锁（RLock）模型下，宠物休眠/让行中复用 orchestration 任务状态机 `SUSPENDED`，主循环 busy 时宠物不抢锁。

#### Scenario: 主循环 busy 让行
- **GIVEN** 主循环 busy 占用资源
- **WHEN** 宠物会话请求执行
- **THEN** 宠物不抢锁，进入让行态（`SUSPENDED`），等待主循环释放资源

#### Scenario: 让行后恢复
- **GIVEN** 宠物会话处于让行态（`SUSPENDED`）
- **WHEN** 主循环释放资源
- **THEN** 宠物会话恢复执行，已完成的子任务结果不丢失

### Requirement: Preference Tracking
系统 SHALL 追踪主 Agent（主人）偏好：宠物观察主人行为与反馈，以 `MemoryEntry.source=user` 落 L2 facts 层，不新造记忆层。

#### Scenario: 记录主人偏好
- **GIVEN** 宠物会话观察到主人行为/反馈
- **WHEN** 提取偏好
- **THEN** 以 `MemoryEntry.source=user` 写入 L2 facts 层，来源可追溯

#### Scenario: 偏好复用
- **GIVEN** L2 facts 层已有主人偏好
- **WHEN** 宠物执行任务或沟通
- **THEN** 复用已记录偏好，行为与反馈符合主人偏好

### Requirement: Three-Entry Activation
系统 SHALL 支持三入口激活宠物会话：`/pet` 斜杠命令（UI 层交互，候选来自 plugin-registry 注册的 command/tool 元数据经统一 API `list_tools` 拉取，不进内核接口）、`pet <verb>` CLI argv（cli-ops-interface `CommandGroup` 扩展）、WebUI 自然语言「启动宠物 + 任务」（经 `UIAPILayer` / `IMGateway.on_message` 消息驱动会话，激活靠 Agent 理解）。

#### Scenario: /pet 斜杠命令激活
- **GIVEN** UI 层输入 `/pet` 触发命令面板
- **WHEN** 选择命令 / 工具候选（经统一 API `list_tools` 拉取）
- **THEN** 激活对应宠物会话，不进内核接口

#### Scenario: pet CLI argv 激活
- **GIVEN** 宿主 CLI 输入 `pet <verb>` 命令
- **WHEN** 解析 argv（cli-ops-interface `CommandGroup` 扩展）
- **THEN** 激活对应宠物会话

#### Scenario: WebUI 自然语言激活
- **GIVEN** WebUI 输入「启动宠物 + 任务」自然语言
- **WHEN** 经 `UIAPILayer` / `IMGateway.on_message` 进入内核 loop，Agent 理解意图
- **THEN** 激活后台宠物会话并绑定任务

### Requirement: Periodic Feedback and Surprise
系统 SHALL 支持宠物定期与主 Agent 沟通/反馈，并基于主人偏好制造惊喜（主人当前不太重要但宠物能代办/取悦的事）。

惊喜 SHALL 以**真实可代办事项**为前提：仅当宠物已积累主人偏好时，SHALL 经**真实 loop** 执行一次代办并回报**其真实结果**；
**无可代办事项时 SHALL NOT 产出**（`surprise()` 返回空）、**SHALL NOT 通知主人**、**SHALL NOT 以通用文案谎报**（账本 E26）。
惊喜的尝试节拍 SHALL 与反馈节拍**同源**（同一反馈周期判据）—— 每周期至多一次，不刷屏。
惊喜为尽力而为的**非关键路径**：其执行失败 SHALL NOT 阻断本次唤醒（`wake()` 照常完成）。

#### Scenario: 定期反馈
- **GIVEN** 宠物会话运行中，达到反馈周期
- **WHEN** 定期沟通/反馈
- **THEN** 宠物向主人汇报后台进展，不阻塞主循环

#### Scenario: 制造惊喜
- **GIVEN** 宠物会话积累了主人偏好
- **WHEN** 发现可代办/取悦主人的事
- **THEN** 宠物经真实 loop 主动执行并制造惊喜，回报**真实执行结果**（非通用文案）给主人

#### Scenario: 无可代办不产出
- **GIVEN** 宠物会话无已记录偏好（无真实可代办事项）
- **WHEN** 到达惊喜尝试节拍
- **THEN** 不产出任何「已安排」文案、不通知主人（不谎报）

#### Scenario: 惊喜失败不阻断唤醒
- **GIVEN** 宠物会话积累了主人偏好
- **WHEN** 惊喜尝试期间 loop 执行失败
- **THEN** 本次唤醒照常完成、不抛出异常（惊喜为非关键路径）

### Requirement: Pet Architecture Layers
系统 SHALL 将宠物实现为解耦的四层架构：基础属性层（角色/性格/喜好/物种）、自主目标循环层、探索工具集层、安全边界层；各层可独立配置与替换

#### Scenario: 四层独立配置与替换
- **GIVEN** 一只已注册宠物
- **WHEN** 系统加载并运行该宠物
- **THEN** 四层各自独立配置，替换任一层不影响其余层

### Requirement: Multi-Pet Management
系统 SHALL 支持同时管理多只宠物，每只宠物拥有独立会话、独立人格、独立任务队列，互不干扰、可独立启停。
宠物注册表 SHALL **跨进程存活**：注册、启停后落盘；新进程加载后可见已注册宠物并对其独立启停。

宠物注册表快照 SHALL 携带每只宠物的**人格**、任务队列与唤醒进度（唤醒计数 / 让行 / 故障 / 状态）；唤醒与任务派发后 SHALL 重新落盘（注册表路径存在时）。新进程恢复后 SHALL 还原人格、队列与计数：SHALL NOT 重放已消费任务，SHALL NOT 丢掉已派发任务。

#### Scenario: 多宠物并行调度
- **GIVEN** 已注册多只宠物
- **WHEN** 系统并行调度多只宠物
- **THEN** 每只独立会话与任务队列，A 宠物异常不影响 B 宠物

#### Scenario: 注册表跨进程存活
- **GIVEN** 某进程激活并注册了一只宠物
- **WHEN** 另一进程加载宠物注册表
- **THEN** 已注册宠物可见（`list`），并可对其独立启停（`stop`）

#### Scenario: 唤醒进度与人格跨进程还原
- **GIVEN** 一只已注册宠物（队首 2 个任务、带人格），被唤醒 1 次
- **WHEN** 同一注册表文件被新进程加载
- **THEN** 剩余任务 1 个、唤醒计数 1、人格字段完整（恢复后的唤醒 prompt 仍含该人格）

### Requirement: Pet Persona and Prompt
系统 SHALL 支持通过 pet.md/prompt 为每只宠物设定角色、性格、喜好，宠物行为与输出风格受其人格约束

人格 SHALL **随会话固定**（persona pinning）：激活时注入的人格 SHALL 随注册表快照落盘，进程恢复后 SHALL 重建同一人格（角色/性格/喜好/prompt 逐字一致）；恢复时显式注入的人格 SHALL 优先于快照。未配置人格的会话 SHALL 保持既有裸任务行为（逐字不变）。

#### Scenario: 人格约束行为
- **GIVEN** 一只宠物配置了 pet.md 人格
- **WHEN** 宠物执行任务并产出行为
- **THEN** 行为与输出风格符合其角色、性格、喜好设定

#### Scenario: 人格跨进程固定
- **GIVEN** 以 pet.md 人格激活并注册宠物
- **WHEN** 新进程从注册表恢复会话并唤醒
- **THEN** 唤醒 prompt 仍含该人格（名称/性格/喜好/prompt），SHALL NOT 退化为裸任务文本

### Requirement: Pet Character Library
系统 SHALL 提供宠物角色库，支持从预置角色模板创建宠物、自定义角色、导入/导出角色定义

#### Scenario: 角色库创建与自定义
- **GIVEN** 用户想新建宠物
- **WHEN** 从角色库选择或自定义角色
- **THEN** 可基于模板创建、自定义并导入导出角色定义

### Requirement: Exploration Toolset
系统 SHALL 为宠物提供受限探索工具集（只读优先），供信息收集与闲逛探索使用，工具清单可配置、需授权

#### Scenario: 受限探索工具集
- **GIVEN** 宠物执行闲逛探索任务
- **WHEN** 调用探索工具
- **THEN** 仅限已授权的只读优先工具，清单可配置

### Requirement: Pet Safety Bounds
系统 SHALL 为宠物行为施加安全边界：只读优先、不可逆操作禁止、爆炸半径可控、越界即暂停并通知主人。

**「暂停」的实现口径**：越界动作 SHALL **不执行**，本轮 SHALL 终止（以终止动作短路本轮），并 SHALL 经通知器**告知主人**（含越界原因）；**会话本身 SHALL 保持 ACTIVE** —— 不得因单次越界转入休眠 / 让行 / 退避态（那需要外部恢复，会让宠物在无人值守时**永久停摆**）。

#### Scenario: 安全边界阻断
- **GIVEN** 宠物拟执行越界/不可逆操作
- **WHEN** 触及安全边界
- **THEN** 操作被阻断、宠物暂停并通知主人

#### Scenario: 越界阻断不楔死会话
- **GIVEN** 一只 ACTIVE 的宠物，其越界动作被安全边界阻断
- **WHEN** 本轮结束
- **THEN** 该动作未执行、本轮终止、主人收到越界原因通知，且会话**仍为 ACTIVE**（下次唤醒照常执行）

### Requirement: Pet Notification
系统 SHALL 支持宠物主动通知主人（如「发现插件X一键生成测试用例，帮你试3次都成功」），通知异步投递、不阻塞主循环

#### Scenario: 异步通知
- **GIVEN** 宠物完成任务发现可回报结果
- **WHEN** 生成通知
- **THEN** 异步投递给主人，主循环不被阻塞

### Requirement: Pet Micro-tasks
系统 SHALL 支持宠物执行日常随机小任务（终端散步、系统小提示、给代码加无厘头注释），其中侵入性任务可配置关闭。每条微任务 SHALL 产生**真实观测或真实副作用**；**无真实产出时 SHALL 返回空、不上报**（SHALL NOT 投出预制文案谎报）。

微任务 SHALL 在宠物**空闲（队列清空入睡）**时经通知器触发一次；`terminal_walk` 只报**命令历史条数**、SHALL NOT 外泄历史内容（历史可能含密钥/隐私）。

#### Scenario: 日常随机微任务
- **GIVEN** 宠物空闲触发日常微任务
- **WHEN** 执行随机小任务
- **THEN** 只执行已启用任务，无厘头注释等侵入性任务可配置关闭

#### Scenario: 空闲入睡前触发微任务
- **GIVEN** 宠物队列清空、即将进入休眠
- **WHEN** 收尾（有通知面）
- **THEN** 触发一次已启用微任务，其**真实产出**经通知器上报

#### Scenario: 无真实产出不谎报
- **GIVEN** 某微任务无真实可交付（历史不可读 / 负载不显著 / 无写回口）
- **WHEN** 触发该微任务
- **THEN** 该微任务返回空、**不上报**，SHALL NOT 投出预制文案

### Requirement: Pet Session Runtime Wiring
系统 SHALL 经组合根为生产激活的宠物会话注入真实依赖：唤醒用的**组合根装配的真实 loop**
（可为宠物**专属 loop**，非 echo 兜底）、记忆后端、受限探索工具集、安全边界与通知器。
经生产入口激活的宠物 SHALL 因此满足「Preference Tracking」与「Background Pet Session Lifecycle」
需求 —— 偏好落 L2 facts 层，唤醒经真实 loop 执行（而非 echo 兜底）。

「真实 loop」SHALL NOT 被读作「主 loop」：宠物与神兽同型，跑在组合根为其装配的**专属 loop** 上
（`beast-mode` spec 明文「独立 `LoopPlugin` 实例」）—— 专属 loop 才承载受限探索工具集与安全边界，
共享主 loop 会使二者不在路径上（见账本 E29）。

宠物经由该 loop 产生的**执行轨迹** SHALL 以**宠物会话标识**归属（条目 `session_id` 等于宠物会话 id），
SHALL NOT 以未归属（空串）形态落库、SHALL NOT 与主线未归属条目**混同**——宠物是后台自治体，
其轨迹不属于任何前台对话会话。宠物**观察到的主人偏好**（`source=user`）为**刻意知识**，
SHALL 保持全局层（未归属），不随本条归属。

宠物经由该 loop 产生的**执行轨迹** SHALL 另落**独立记忆命名空间**（条目 `source=pet`），与主 Agent
（`source=loop`）、神兽（`source=beast.<agent_id>`）三者互不混同——宠物是后台自治体，其自治所得
SHALL NOT 被主 Agent（及神兽）的检索面吸收为自身事实：上述 Agent 的记忆检索面 SHALL **封存**
`pet` 命名空间。该封存 SHALL NOT 使宠物读不到**自身**轨迹：宠物的上下文装配 SHALL 在排除面内
**放行自身**命名空间。本条的命名空间归属与上段的会话归属 SHALL 同时成立、互不替代——会话标识隔离
**会话个体**（哪只宠物），命名空间隔离 **Agent 身份**（宠物 / 神兽 / 主 Agent）。

#### Scenario: 生产激活的宠物偏好落 L2
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活一只宠物并观察主人偏好
- **THEN** 偏好以 `MemoryEntry.source=user` 写入运行系统共享的 L2 facts 层（全局层，未归属）

#### Scenario: 生产激活的宠物唤醒走真实 loop
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活的宠物被唤醒
- **THEN** 唤醒经组合根装配的**真实 loop**（宠物专属，非 echo 兜底 loop）执行自治任务

#### Scenario: 宠物轨迹以宠物会话归属
- **GIVEN** 经组合根装配的运行系统，一只宠物被唤醒并跑完一轮自治任务
- **WHEN** 该轮轨迹沉淀进记忆
- **THEN** 条目 `session_id` 等于该宠物会话 id，**不等于**空串，前台会话检索不到它

#### Scenario: 宠物轨迹落独立命名空间
- **GIVEN** 经组合根装配的运行系统，一只宠物被唤醒并跑完一轮自治任务
- **WHEN** 该轮轨迹沉淀进记忆
- **THEN** 条目 `source=pet`，与主 Agent（`source=loop`）命名空间隔离

#### Scenario: 主 Agent 检索面封存宠物命名空间
- **GIVEN** 库中已沉淀 `source=pet` 的宠物轨迹（另含主线 `source=loop` 条目）
- **WHEN** 主 Agent 按任务检索（**未带会话标识**，即会话面不过滤）
- **THEN** `source=pet` 条目**不出现**，主线条目**仍出现**

#### Scenario: 宠物自身轨迹可召回
- **GIVEN** 宠物自身已有 `source=pet` 轨迹沉淀，且库中另有 `source=beast.*` 条目
- **WHEN** 该宠物装配上下文并检索
- **THEN** 自身 `source=pet` 条目**出现**（排除面内放行自身命名空间）；`source=beast.*` 条目**不出现**

#### Scenario: 主人偏好不受命名空间封存影响
- **GIVEN** 宠物已观察到主人偏好（`source=user`，全局层）
- **WHEN** 主 Agent 按任务检索
- **THEN** 该偏好条目**仍可出现**（刻意知识，不随宠物命名空间封存）

### Requirement: Pet Control Surface
系统 SHALL 提供统一的宠物**控制面**，让宿主层（前台 `/pet [cmd]`、`pet <verb>` CLI argv、WebUI 自然语言）
在宠物运行期间**随时**查看状态、让它停止工作 / 换一件活 / 睡觉 / 叫醒。控制面 SHALL 由**单一门面**
（`PetControl`：verb → 会话操作）收口，CLI 与 `UIAPILayer` 复用同一实现，SHALL NOT 各自实现一套。

控制面 SHALL 支持动词 `status` / `sleep` / `wake` / `assign` / `stop`；**寻址**规则：未指定会话且仅注册一只
宠物 ⇒ 默认作用于该宠物；多只而未指定 ⇒ 拒绝并列出可选会话（SHALL NOT 猜测）；指定但未注册 ⇒ 抛结构化
`PET_NOT_FOUND`（SHALL NOT 静默成功）。`status` SHALL 返回结构化字段（会话 id / 状态 / 是否休眠 / 待办数 /
唤醒计数 / 故障），SHALL NOT 外泄主人偏好与任务正文。控制面 SHALL 只作用**本进程**已注册会话
（跨进程注册表是快照，不驱动 live 会话 —— 有意不做跨进程）。

`wake` 对 `ACTIVE` 会话 SHALL 清让行（既有语义），对 `BACKOFF` 会话 SHALL 执行故障恢复（`BACKOFF → ACTIVE`、清故障）。控制面的变更动词（`sleep` / `wake` / `assign` / `stop`）SHALL 在返回前把注册表落盘（注册表路径存在时），使新进程可见其效果。

#### Scenario: 查看状态
- **GIVEN** 本进程有一只运行中的宠物
- **WHEN** 前台 `/pet status`
- **THEN** 返回结构化状态（会话 id / 状态 / 是否休眠 / 待办数 / 唤醒计数 / 故障），不含主人偏好与任务正文

#### Scenario: 睡觉与叫醒
- **GIVEN** 一只 `ACTIVE` 的宠物
- **WHEN** 控制面 `sleep`，其后 `wake`
- **THEN** `sleep` 置让行态（休眠，后续唤醒被拒 `PET_YIELDING`）；`wake` 清让行态恢复

#### Scenario: 换一件活
- **GIVEN** 一只宠物（可处于让行/休眠）
- **WHEN** 控制面 `assign` 一件新任务
- **THEN** 新任务入队并清让行态（自动唤醒），下次唤醒消费之

#### Scenario: 单宠物默认寻址
- **GIVEN** 本进程仅注册一只宠物
- **WHEN** 控制动词未指定会话
- **THEN** 默认作用于该宠物

#### Scenario: 多宠物未指定被拒
- **GIVEN** 本进程注册多只宠物
- **WHEN** 控制动词未指定会话
- **THEN** 拒绝并列出可选会话 id，SHALL NOT 猜测

#### Scenario: 未知会话被拒
- **GIVEN** 一个未注册的会话 id
- **WHEN** 任一控制动词
- **THEN** 抛结构化 `PET_NOT_FOUND`（CLI 退出码 1），SHALL NOT 静默成功

#### Scenario: 退避恢复
- **GIVEN** 一只 `BACKOFF` 宠物（故障已记录）
- **WHEN** 控制面 `wake`
- **THEN** 状态恢复为 `ACTIVE`、故障字段清空，随后可派发与唤醒

### Requirement: Task Result Query

系统 SHALL 提供宠物**最近一次任务结果**的只读查询面：`PetControl.result(session_id=None)` SHALL 返回结构化字段
（会话 id / 是否有结果 / 结果正文 / 成败），并经 CLI `pet result` 与 `UIAPILayer` **复用同一实现**（照既有单一门面
口径）。寻址规则 SHALL 与既有控制动词**逐字一致**（未指定且仅注册一只 ⇒ 默认作用于该宠物；多只未指定 ⇒ 拒绝并
列出可选会话；指定但未注册 ⇒ 抛结构化 `PET_NOT_FOUND`）。该查询面 SHALL 只作用**本进程**已注册会话，SHALL 只
暴露**最近一次**结果，SHALL NOT 落盘（不进 `snapshot` / 跨进程注册表）。该查询面 SHALL NOT 改变 `status` 的返回面
—— `status` SHALL 仍**不含**主人偏好与任务正文。无结果时（会话尚未唤醒过）SHALL 明确报「无结果」，SHALL NOT 编造正文。

#### Scenario: 查询最近结果
- **GIVEN** 本进程有一只完成过一轮唤醒的宠物
- **WHEN** 控制面 `result`（CLI `pet result` / 前台 `/pet result`）
- **THEN** 返回结构化字段（会话 id / 是否有结果 / 结果正文 / 成败）

#### Scenario: status 返回面不受影响
- **GIVEN** 一只已有最近结果的宠物
- **WHEN** 控制面 `status`
- **THEN** 返回字段与既有口径**逐字不变**，SHALL NOT 含主人偏好与任务正文

#### Scenario: 无结果不谎报
- **GIVEN** 一只尚未唤醒过的宠物
- **WHEN** 控制面 `result`
- **THEN** 明确「无结果」（`has_result=false`），SHALL NOT 编造正文

#### Scenario: 未知会话被拒
- **GIVEN** 一个未注册的会话 id
- **WHEN** 控制面 `result`
- **THEN** 抛结构化 `PET_NOT_FOUND`，SHALL NOT 静默成功
