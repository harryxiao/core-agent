# Tasks

## 1. 最小闭环（P0）

- [ ] 1.1 以官方 a2a-sdk 搭建云端 Server ↔ PC Client 最小闭环（AgentCard 发现 → SendMessage → 流式订阅进度）
- [ ] 1.2 实现 JSON-RPC 2.0 over HTTP(S) 默认绑定（流式走 SSE）
- [ ] 1.3 AgentCard 签名与验证
- [ ] 1.4 OAuth2 / mTLS 鉴权接入 + 最小权限 scope 对接 permission 链路

## 2. MCP 能力暴露（P1）

- [ ] 2.1 PC/嵌入式本地能力经 MCP 暴露（stdio 起步，逐步 Streamable HTTP）
- [ ] 2.2 A2A Server 内部经 MCP 调用底层工具（FR-7）

## 3. 移动瘦客户端（P2）

- [ ] 3.1 移动端 A2A 瘦客户端（REST 绑定 + 推送通知）

## 4. P2P 传输优化（P3，可选）

- [ ] 4.1 设备间 P2P 直连（公钥寻址 + 打洞 + relay 回退），并自建基准测试验证延迟收益
