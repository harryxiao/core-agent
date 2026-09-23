# Distributed Specification

## Purpose
分布式协作层让 Core-Agent 从单设备循环升级为可跨设备协作的分布式 Agent，提供 A2A 双向互调、AgentCard 发现与签名、协议绑定、安全鉴权、多设备拓扑、可选 P2P 优化、A2A↔MCP 互补七层能力，确保跨设备调用可控、可审计、可追溯。

## Requirements

### Requirement: A2A 双向互调
系统 SHALL 同时具备 A2A Client 与 A2A Server 两种角色：作为 Client 可委派任务给外部 Agent（Claude Code / Codex / Kilo 等），作为 Server 可对外暴露自身能力被外部 Agent 调用。

#### Scenario: 委派外部 Agent
- **GIVEN** Core-Agent 需要调用外部 Agent 完成某任务
- **WHEN** 通过 A2A Client 向目标 Agent 的 AgentCard 声明的接口发送任务
- **THEN** 任务被委派，外部 Agent 开始执行并可通过流式或推送回报进度

#### Scenario: 对外暴露能力
- **GIVEN** 外部 Agent 需要调用 Core-Agent 的能力
- **WHEN** 通过 A2A Server 接口发起调用
- **THEN** Core-Agent 作为 Server 接受任务并执行，结果经 A2A 协议返回

### Requirement: AgentCard 发现与签名
系统 SHALL 以 AgentCard 声明自身的 AgentProvider / AgentCapabilities / AgentSkill / AgentInterface，并支持 AgentCard 签名与验证，供对等 Agent 发现与协商。

#### Scenario: 能力发现
- **GIVEN** 对等 Agent 需要发现 Core-Agent 的能力
- **WHEN** 获取并解析 Core-Agent 的 AgentCard
- **THEN** 得到可调用的能力/技能/接口清单，据此协商交互方式

#### Scenario: 卡片签名验证
- **GIVEN** 对等 Agent 提供了已签名的 AgentCard
- **WHEN** Core-Agent 验证该签名
- **THEN** 签名有效则接受该 Agent 的身份与能力声明，无效则拒绝

### Requirement: 协议绑定
系统 SHALL 支持 A2A 的三种协议绑定：JSON-RPC 2.0 over HTTP(S) 为默认/推荐绑定（流式用 Server-Sent Events），gRPC 与 HTTP+JSON/REST 为备选，并保留自定义绑定能力。

#### Scenario: 默认 JSON-RPC 绑定
- **GIVEN** 一次 A2A 交互
- **WHEN** 未显式指定绑定方式
- **THEN** 系统以 JSON-RPC 2.0 over HTTP(S) 承载核心操作，流式任务走 SSE

#### Scenario: 备选绑定
- **GIVEN** 对等 Agent 仅支持 gRPC 或 REST
- **WHEN** 发起交互
- **THEN** 系统按对端声明的绑定（gRPC 或 REST）完成同套核心操作

### Requirement: 安全鉴权
系统 SHALL 支持 A2A 的 OAuth2 / mTLS / APIKey / OpenIdConnect 鉴权方案，跨设备调用按最小权限 scope 授权，高危操作复用既有 permission 审批链路。

#### Scenario: 双向认证
- **GIVEN** 云端与嵌入式设备间需下发敏感指令
- **WHEN** 建立连接
- **THEN** 优先采用 mTLS 双向认证，且仅授予最小权限 scope

#### Scenario: 最小权限授权
- **GIVEN** 外部 Agent 调用某能力
- **WHEN** 该调用超出已授权 scope
- **THEN** 调用被拒绝，并记录审计日志（来源 `a2a:<peer>`）

### Requirement: 多设备拓扑角色
系统 SHALL 支持云端 / 个人 PC / 移动终端 / 嵌入式四类设备的分布式拓扑：云端为 A2A Server+控制面+relay，PC 为本地 Agent（工具留本机），移动端为 A2A 瘦客户端，嵌入式为 MCP Server 能力提供者，实现控制面/执行面分离。

#### Scenario: 控制面执行面分离
- **GIVEN** 任务在云端控制面被委派
- **WHEN** 执行面在 PC 本机（文件系统/MCP 工具留本机）
- **THEN** 云端只承载协调与进度，本机执行结果回传云端

#### Scenario: 移动瘦客户端
- **GIVEN** 用户在移动终端发起协作
- **WHEN** 通过 A2A 瘦客户端发现并委派任务
- **THEN** 移动端仅做发现/委派/订阅进度/展示，不承载重型执行

### Requirement: 可选 P2P 传输优化
系统 MAY 支持可选的设备间 P2P 直连优化：按公钥寻址、NAT 打洞直连优先、失败回退 relay、QUIC 传输；该优化为可选传输层，不改变上层 A2A 协议行为。

#### Scenario: 打洞直连优先
- **GIVEN** 两设备尝试 P2P 直连
- **WHEN** NAT 打洞成功
- **THEN** 走直连传输；打洞失败则回退 relay 转发，上层 A2A 行为不变

### Requirement: A2A 与 MCP 互补
系统 SHALL 遵循 A2A 与 MCP 的互补关系：A2A Server 内部经 MCP 调用底层工具/数据完成任务，Agent 间协作走 A2A、能力调用走 MCP。

#### Scenario: Server 内部经 MCP 调用工具
- **GIVEN** A2A Server 收到一个需底层工具完成的任务
- **WHEN** 执行该任务
- **THEN** 通过 MCP 调用本地/远程工具与数据源完成，再经 A2A 回传结果

### Requirement: A2A 连接管理
系统 SHALL 管理 A2A 对等连接的完整生命周期：连接保活（keepalive 心跳/heartbeat）与超时（timeout）检测、断线自动重连（reconnect，指数退避）、连接与任务资源显式释放、委派重试幂等（同一任务不重复执行）。

#### Scenario: 心跳保活
- **GIVEN** 一次 A2A 对等连接已建立
- **WHEN** 超过心跳（heartbeat）间隔未收到对端消息
- **THEN** 发送 keepalive 心跳探测对端存活，连续失败则判定连接失效并触发重连

#### Scenario: 断线自动重连
- **GIVEN** A2A 连接意外断开
- **WHEN** 检测到断线
- **THEN** 按指数退避自动 reconnect，重连成功后恢复会话，达到最大重试次数则标记连接失败

#### Scenario: 调用超时
- **GIVEN** 委派任务或调用外部 Agent
- **WHEN** 响应超过超时（timeout）阈值
- **THEN** 判定调用超时，取消等待并释放该次调用占用资源

#### Scenario: 资源释放
- **GIVEN** A2A 连接关闭或任务结束
- **WHEN** 执行清理
- **THEN** 显式释放该连接与任务占用的连接、会话与内存资源，避免泄漏

#### Scenario: 委派重试幂等
- **GIVEN** 委派请求因超时或断线需重试
- **WHEN** 携带同一任务 ID 重新委派
- **THEN** 对端按任务 ID 幂等去重，同一任务不重复执行，仅返回首次执行结果
