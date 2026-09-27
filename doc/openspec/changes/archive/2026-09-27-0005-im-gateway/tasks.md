# Tasks

> 注：本 Phase 按项目「不锁选型」立场，im 仅落**可注入抽象**（IMGateway Plugin + IMProvider Protocol，无真实平台 SDK）。
> 下方标注「真实后端未接」的项 = 抽象（数据模型 + 注入 seam + 白名单/确认/幂等）已落地，真实平台 SDK 留待后续。

## 1. IMGateway 骨架（P1）

- [x] 1.1 定义 IMGateway 抽象与 Message/Session 数据模型
- [x] 1.2 实现 Provider 注册与消息 → 内核会话适配（register + on_message → _session_for + run_session）
- [x] 1.3 实现内核回推 → 平台消息编码（reply → provider.send）

## 2. Telegram/Discord 接入（P1）

- [ ] 2.1 实现 Telegram Bot API Provider（webhook / 长轮询）—— 真实后端未接：IMProvider Protocol + register 注入 seam 已落地，真实 Telegram SDK 未接
- [ ] 2.2 实现 Discord Bot API Provider（网关事件）—— 真实后端未接：真实 Discord SDK 未接
- [x] 2.3 白名单鉴权（on_message 白名单校验 → IM_NOT_WHITELISTED）；群聊 @ 触发 deferred（真实平台未接）

## 3. 飞书/微信接入（P2）

- [ ] 3.1 实现飞书开放平台长连接 WebSocket Provider（事件订阅 + 心跳重连）—— 真实后端未接：真实飞书 SDK 未接
- [ ] 3.2 实现企业微信/公众号合规通道 Provider—— 真实后端未接：真实企微 SDK 未接
- [x] 3.3 实现高危操作 IM 内二次确认（approve → confirm → ApprovalWorkflow，IM_CONFIRM_DENIED/TIMEOUT）

## 4. 发布与集成（P3）

- [ ] 4.1 提供各平台接入配置模板与部署说明—— 真实后端未接：真实平台配置模板未接
- [x] 4.2 会话隔离（Session 按 平台:用户 独立）+ 断线隔离（IM_PLATFORM_DISCONNECTED）；断线重连压力用例 deferred
- [x] 4.3 抽象层端到端用例（FakeProvider：发消息 → loop → 确认门 → 回推）跑通；真实平台端到端 deferred
