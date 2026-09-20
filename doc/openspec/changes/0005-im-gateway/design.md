# Design

## Context

core-agent 目前有「人 → core-agent」三入口（CLI/Web/Desktop，0003）与「机器 → core-agent」入口（MCP Server，0004），但都要求用户坐在电脑前。社交 IM（微信/飞书/Telegram/Discord）是最高频的随身触点，把 core-agent 接到 IM 后，用户在手机上即可远程驱动同一内核，形成「随身 → core-agent」入口，与既有入口对称。

## Decisions

- **统一 IMGateway 抽象**：不复制内核逻辑，各平台差异收敛在 Provider 适配器（收消息 → 统一 Message 事件 → 内核会话；内核回推 → 适配器编码 → 平台消息）。
- **分平台接入方式**：Telegram/Discord 用官方 Bot API（webhook 或长轮询，零内网穿透）；飞书用开放平台长连接 WebSocket（事件订阅）；微信用企业微信/公众号合规通道（个人号封号风险，明确不采用）。
- **复用安全链路**：IM 远程调用走同一 invoke 链路（permission 确认门 + observability 审计，来源 `im:<platform>:<user_id>`），不绕过内核。
- **身份白名单 + 群 @ 触发**：白名单用户可触发；群聊仅 @ 机器人时响应，防止误触与陌生人操控。
- **会话按 平台:用户/群 隔离**：每连接独立会话，故障熔断隔离，不拖垮主循环。

## Risks / Trade-offs

- **越权/冒充**：IM 账号被盗即等于 agent 入口失守——用白名单 + 高危操作二次确认兜底。
- **个人微信封号**：个人号接入违反平台规则，明确走企业微信/公众号合规通道。
- **长连接稳定性**：飞书 WebSocket 需心跳保活与断线重连，否则消息丢失。
- **上下文膨胀**：群聊多话题易串扰——按会话隔离 + 上下文压实机制缓解。

## Open Questions

- 微信「企业微信 vs 公众号」具体选型（P2 按目标用户定）。
- 是否支持 IM 内多轮交互式确认（如按钮/键盘确认）——初版文本确认，后续按需评估。
