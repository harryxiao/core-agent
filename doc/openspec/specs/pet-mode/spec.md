# Pet Mode Specification

## Purpose

宠物模式（pet-mode）为 core-agent 提供后台自治循环扩展与宿主层三入口交互面：以统一 pet session 生命周期承载重复简单任务（信息收集 / 闲逛探索）、偏好追踪、定期反馈/惊喜，低优先级让行不阻塞主循环，三入口（/pet 斜杠命令、pet <verb> CLI argv、WebUI 自然语言）激活后台宠物会话，相当于"人类养宠物"——做当前不太重要的事、了解主人偏好、制造惊喜。

## Requirements

### Requirement: Background Pet Session Lifecycle
系统 SHALL 管理宠物会话的启动、休眠、恢复、异常退避、终止全生命周期，每次唤醒复用 `Loop.run()` 同步薄壳（asyncio.run 桥接）逐次执行，异常退避不残留半运行状态。

#### Scenario: 启动与唤醒
- **GIVEN** 通过任一入口激活宠物会话
- **WHEN** 宠物会话启动 / 每次唤醒
- **THEN** 经 `Loop.run()` 同步薄壳执行一次自治任务，会话状态一致

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

#### Scenario: 定期反馈
- **GIVEN** 宠物会话运行中，达到反馈周期
- **WHEN** 定期沟通/反馈
- **THEN** 宠物向主人汇报后台进展，不阻塞主循环

#### Scenario: 制造惊喜
- **GIVEN** 宠物会话积累了主人偏好
- **WHEN** 发现可代办/取悦主人的事
- **THEN** 宠物主动执行并制造惊喜，结果反馈给主人

### Requirement: Pet Architecture Layers
系统 SHALL 将宠物实现为解耦的四层架构：基础属性层（角色/性格/喜好/物种）、自主目标循环层、探索工具集层、安全边界层；各层可独立配置与替换

#### Scenario: 四层独立配置与替换
- **GIVEN** 一只已注册宠物
- **WHEN** 系统加载并运行该宠物
- **THEN** 四层各自独立配置，替换任一层不影响其余层

### Requirement: Multi-Pet Management
系统 SHALL 支持同时管理多只宠物，每只宠物拥有独立会话、独立人格、独立任务队列，互不干扰、可独立启停。
宠物注册表 SHALL **跨进程存活**：注册、启停后落盘；新进程加载后可见已注册宠物并对其独立启停。

#### Scenario: 多宠物并行调度
- **GIVEN** 已注册多只宠物
- **WHEN** 系统并行调度多只宠物
- **THEN** 每只独立会话与任务队列，A 宠物异常不影响 B 宠物

#### Scenario: 注册表跨进程存活
- **GIVEN** 某进程激活并注册了一只宠物
- **WHEN** 另一进程加载宠物注册表
- **THEN** 已注册宠物可见（`list`），并可对其独立启停（`stop`）

### Requirement: Pet Persona and Prompt
系统 SHALL 支持通过 pet.md/prompt 为每只宠物设定角色、性格、喜好，宠物行为与输出风格受其人格约束

#### Scenario: 人格约束行为
- **GIVEN** 一只宠物配置了 pet.md 人格
- **WHEN** 宠物执行任务并产出行为
- **THEN** 行为与输出风格符合其角色、性格、喜好设定

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
系统 SHALL 支持宠物执行日常随机小任务（终端散步、系统小提示、给代码加无厘头注释），其中侵入性任务可配置关闭

#### Scenario: 日常随机微任务
- **GIVEN** 宠物空闲触发日常微任务
- **WHEN** 执行随机小任务
- **THEN** 只执行已启用任务，无厘头注释等侵入性任务可配置关闭

### Requirement: Pet Session Runtime Wiring
系统 SHALL 经组合根为生产激活的宠物会话注入真实依赖：唤醒用的主 loop、记忆后端、
受限探索工具集、安全边界与通知器。经生产入口激活的宠物 SHALL 因此满足
「Preference Tracking」与「Background Pet Session Lifecycle」需求 —— 偏好落 L2 facts 层，
唤醒经真实 loop 执行（而非 echo 兜底）。

#### Scenario: 生产激活的宠物偏好落 L2
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活一只宠物并观察主人偏好
- **THEN** 偏好以 `MemoryEntry.source=user` 写入运行系统共享的 L2 facts 层

#### Scenario: 生产激活的宠物唤醒走真实 loop
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活的宠物被唤醒
- **THEN** 唤醒复用运行系统的主 loop（非 echo 兜底 loop）执行自治任务
