# Tasks

> 注：本 Phase 按项目「不锁选型」立场，distributed 仅落**可注入抽象**（无真实 a2a-sdk / 网络 / 协议 / 密钥代码）。
> 下方标注「真实后端未接」的项 = 抽象（数据模型 + 注入 seam + 状态机）已落地，真实传输/协议/密码学留待 Phase 7。

## 1. 最小闭环（P0）

- [ ] 1.1 以官方 a2a-sdk 搭建云端 Server ↔ PC Client 最小闭环（AgentCard 发现 → SendMessage → 流式订阅进度）—— 真实后端未接：仅 A2AClient/A2AServer + 注入 transport（无 a2a-sdk / 云）
- [ ] 1.2 实现 JSON-RPC 2.0 over HTTP(S) 默认绑定（流式走 SSE）—— 真实后端未接：仅协议绑定常量，无 JSON-RPC 2.0 / HTTP / SSE 线协议
- [x] 1.3 AgentCard 签名与验证—— 验证流程（canonical + verify + 未签名/坏签名 → A2A_CARD_INVALID）已落地并测试；签名算法经注入 signer/verifier，未落真实密钥
- [ ] 1.4 OAuth2 / mTLS 鉴权接入 + 最小权限 scope 对接 permission 链路—— 真实后端未接：仅注入 authenticator/policy 回调，无 OAuth2/mTLS，未接 permission

## 2. MCP 能力暴露（P1）

- [ ] 2.1 PC/嵌入式本地能力经 MCP 暴露（stdio 起步，逐步 Streamable HTTP）—— 本 Phase 未实施
- [ ] 2.2 A2A Server 内部经 MCP 调用底层工具（FR-7）—— 真实后端未接：仅注入 tool_caller 回调，未接 MCP

## 3. 移动瘦客户端（P2）

- [ ] 3.1 移动端 A2A 瘦客户端（REST 绑定 + 推送通知）—— 本 Phase 未实施

## 4. P2P 传输优化（P3，可选）

- [ ] 4.1 设备间 P2P 直连（公钥寻址 + 打洞 + relay 回退），并自建基准测试验证延迟收益—— 真实后端未接：仅 route() 返回 "direct"/"relay" 字符串，无打洞/relay/基准测试
