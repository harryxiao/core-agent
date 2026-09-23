A2A 连接管理：对等连接的保活/心跳、断线重连、超时、资源释放与委派重试幂等。（来源：架构查漏补缺探索结论，2026-09-22）

## ADDED Requirements

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
