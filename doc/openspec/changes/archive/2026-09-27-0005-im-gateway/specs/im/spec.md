IM 网关（社交 IM 消息网关）让用户通过微信/飞书/Telegram/Discord 远程驱动 core-agent：消息驱动会话、统一 IMGateway 抽象接入多平台、身份白名单鉴权、走同一 invoke 安全链路、会话隔离容错。

## ADDED Requirements

### Requirement: 多平台统一接入
系统 SHALL 提供统一 IMGateway 抽象屏蔽各平台协议差异，新增平台仅需实现 Provider 适配器，不改动内核。

#### Scenario: 新增平台零侵入
- **GIVEN** 需接入一个新的社交 IM 平台
- **WHEN** 开发者实现该平台的 Provider 适配器并注册
- **THEN** 内核 loop、工具链、记忆与权限链路无需改动即可复用

### Requirement: 消息驱动会话
系统 SHALL 将 IM 消息映射为内核会话：入站消息进入同一 loop 执行，执行结果回推到来源会话；同一会话/群内多轮对话保持上下文。

#### Scenario: 发消息即会话
- **GIVEN** 用户在 IM 中向机器人发送一条消息
- **WHEN** 消息被网关接收
- **THEN** core-agent 在同一 loop 内执行并回推结果

#### Scenario: 多轮上下文保持
- **GIVEN** 同一用户/群内连续多轮对话
- **WHEN** 用户继续追问
- **THEN** 系统按会话/群保持上下文，不重复询问已给信息

#### Scenario: 重复消息幂等
- **GIVEN** 同一消息因网络重试或平台重推被重复投递
- **WHEN** 网关收到重复消息
- **THEN** 按消息唯一标识去重，同一消息仅入 loop 一次，重复投递被忽略

### Requirement: 分平台接入
系统 SHALL 按各平台官方能力接入：Telegram/Discord 用官方 Bot API（webhook 或长轮询）、飞书用开放平台长连接 WebSocket（事件订阅）、微信用企业微信/公众号等合规通道；个人号接入因封号风险不予采用。

#### Scenario: 官方通道接入
- **GIVEN** 各平台已配置机器人凭证与回调
- **WHEN** 平台用户与机器人交互
- **THEN** 消息经官方通道进入网关并回推

#### Scenario: 个人号拒绝
- **GIVEN** 有人提出用个人微信账号直接接入
- **WHEN** 评估接入方式
- **THEN** 因封号风险不采用，改用企业微信/公众号合规通道

### Requirement: 身份绑定与白名单
系统 SHALL 对远程控制入口做身份鉴权：仅白名单用户（及群内 @ 机器人）可触发执行，防止陌生人操控。

#### Scenario: 白名单放行
- **GIVEN** 白名单内用户向机器人发消息
- **WHEN** 网关接收
- **THEN** 正常进入 loop 执行

#### Scenario: 非白名单拒绝
- **GIVEN** 非白名单用户向机器人发消息
- **WHEN** 网关接收
- **THEN** 不执行，返回拒绝提示（不暴露内部信息）

### Requirement: 安全约束透传
系统 SHALL 使 IM 远程调用走与本地一致的 invoke 链路：只读/低危操作放行，高危操作在 IM 内二次确认或拒绝，全部调用标注来源并审计落盘。

#### Scenario: 高危操作确认
- **GIVEN** IM 用户触发删除/执行等高危工具
- **WHEN** 执行前
- **THEN** 在 IM 内推送确认请求，确认后才执行

#### Scenario: 审计落盘
- **GIVEN** IM 用户完成任意调用
- **WHEN** 调用结束
- **THEN** 审计记录标注来源 `im:<platform>:<user_id>`

### Requirement: 会话隔离与容错
系统 SHALL 为每个平台/用户建立独立会话，多平台多用户并发互不串扰；单连接/单平台故障熔断隔离，不拖垮主循环。

#### Scenario: 多用户隔离
- **GIVEN** 多个 IM 平台与用户并发交互
- **WHEN** 各自调用
- **THEN** 会话状态互不串扰

#### Scenario: 平台断线重连
- **GIVEN** 某平台长连接断开
- **WHEN** 连接异常
- **THEN** 该平台会话隔离重连，不影响其他平台与主循环

#### Scenario: 重连退避
- **GIVEN** 某平台长连接断开后进入重连
- **WHEN** 连续重连失败
- **THEN** 按指数退避策略重连（间隔递增并设上限），避免频繁重连冲击平台服务；期间该平台会话保持挂起，不丢消息

