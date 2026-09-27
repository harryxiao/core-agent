# Change: 社交 IM 消息网关（远程控制入口）

## Why

core-agent 已具备「人 → core-agent」三入口（CLI / Web / Desktop，0003）与「机器 → core-agent」入口（MCP Server，0004）。但用户无法在不打开电脑终端/网页的情况下远程驱动 agent：需要在微信、飞书、Telegram、Discord 等日常社交 IM 里直接对话、下达任务、接收结果。

补齐 IM 网关后，core-agent 形成「随身 → core-agent」入口，随时随地在手机 IM 里驱动同一内核，与既有入口对称。

## What Changes

- 新增 `im` capability：统一 IMGateway 抽象 + 分平台 Provider 适配器
- 消息映射为内核会话，结果回推到来源会话，多轮上下文保持
- 身份白名单鉴权 + 高危操作 IM 内二次确认 + 审计来源标注
- 分平台接入：Telegram/Discord 官方 Bot API、飞书长连接 WebSocket、企业微信/公众号合规通道

## Impact

- **Affected specs**：`im`（新增 capability）
- **Affected specs (integration)**：`permission` / `observability` / `loop`（远程调用复用同一 invoke 链路与横切能力）
- **Affected code**：新增 `src/im/`（IMGateway 抽象、Provider 适配器、会话管理、回调服务）；内核层不改动
- **Dependencies**：依赖 0001 主轴（L1 工具层）+ 0002 横切（复用 permission/observability/constraints）
