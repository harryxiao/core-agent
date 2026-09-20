# Tasks

## 1. IMGateway 骨架（P1）

- [ ] 1.1 定义 IMGateway 抽象与 Message/Session 数据模型
- [ ] 1.2 实现 Provider 注册与消息 → 内核会话适配
- [ ] 1.3 实现内核回推 → 平台消息编码

## 2. Telegram/Discord 接入（P1）

- [ ] 2.1 实现 Telegram Bot API Provider（webhook / 长轮询）
- [ ] 2.2 实现 Discord Bot API Provider（网关事件）
- [ ] 2.3 实现群聊 @ 触发与白名单鉴权

## 3. 飞书/微信接入（P2）

- [ ] 3.1 实现飞书开放平台长连接 WebSocket Provider（事件订阅 + 心跳重连）
- [ ] 3.2 实现企业微信/公众号合规通道 Provider
- [ ] 3.3 实现高危操作 IM 内二次确认

## 4. 发布与集成（P3）

- [ ] 4.1 提供各平台接入配置模板与部署说明
- [ ] 4.2 会话隔离与断线重连压力用例
- [ ] 4.3 端到端用例（IM 发消息 → loop 执行 → 确认门 → 回推 → 审计）
