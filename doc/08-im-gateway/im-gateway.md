# IM 网关模式：让用户通过社交 IM 随身驱动 core-agent

> 对应规格：`doc/openspec/specs/im/spec.md` ｜ 变更提案：`doc/openspec/changes/0005-im-gateway/`
> 本方案文档对应 ADR-0018 ~ 0020

---

## 1. 定位与场景

core-agent 已有三类「**人 → core-agent**」入口（CLI / Web / Desktop，见 `06-ui-frontend/ui-architecture.md`）与「**机器 → core-agent**」入口（MCP Server，见 `07-mcp-server/mcp-server.md`），但都要求用户坐在电脑前。

> **IM 网关模式**：让 core-agent 接入微信 / 飞书 / Telegram / Discord 等社交 IM，用户在手机聊天窗口发消息即可远程驱动同一内核，形成「**随身 → core-agent**」入口。

典型场景：

| 场景 | 说明 |
|---|---|
| 随身遥控 | 外出时用手机 IM 下达任务、接收执行结果与告警，无需打开电脑 |
| 群内协作 | 在群聊中 @ 机器人触发任务，结果回推到群，多人共享执行过程 |
| 告警触达 | agent 长时间运行的结果/异常主动推送到个人或群 |

---

## 2. 与既有入口的对称关系

core-agent 的入口全景：

| 入口 | 方向 | 承载 | 模块 |
|---|---|---|---|
| CLI / Web / Desktop | 人 → core-agent | 本机交互 | 06-ui-frontend |
| MCP Server | 机器 → core-agent | 外部 Agent 挂载 | 07-mcp-server |
| **IM 网关** | **随身 → core-agent** | 社交 App 远程控制 | **08-im-gateway** |

三类入口复用同一内核、同一 ToolProvider、同一 invoke 安全链路，差异仅在前端接入层。

---

## 3. 架构

```
                     ┌──────────────────────────────────────────────┐
  社交 IM 用户       │                 core-agent 内核               │
 (微信/飞书/          │                                              │
  Telegram/Discord)  │   ┌───────────────┐   ┌───────────────────┐  │
      │              │   │  IMGateway    │──▶│ 会话/loop 调度     │  │
      │ 消息          │   │ (统一抽象)    │   │                   │  │
      ├─ 消息 ──────▶│   └──────┬────────┘   └─────────┬─────────┘  │
      │              │     Provider 适配器             │ invoke     │
      │              │   (Telegram/Discord/            ▼            │
      │              │    飞书/企业微信)       ┌──────────────────┐  │
      │              │                        │ 统一调用链路       │  │
      │ ◀── 回推 ────┤                        │ permission 确认门  │  │
      │              │                        │ observability 审计 │  │
      └──────────────┘                        └──────────────────┘  │
                    └──────────────────────────────────────────────┘
```

**核心原则**：IM 网关只是**入口适配层**，不是新内核。入站消息翻译成与本地一致的会话事件进入 loop 执行，
结果经 Provider 编码回推；所有远程调用走 permission / observability 同一链路，审计来源 `im:<platform>:<user_id>`。

---

## 4. 平台接入方式

| 平台 | 接入方式 | 特点 |
|---|---|---|
| Telegram | 官方 Bot API（webhook / 长轮询） | 零内网穿透，海外可用 |
| Discord | 官方 Bot API（Gateway 事件） | 零内网穿透，海外可用 |
| 飞书 | 开放平台长连接 WebSocket（事件订阅） | 长连接免公网回调，需心跳保活 + 断线重连 |
| 微信 | 企业微信 / 公众号（合规通道） | 个人号接入有封号风险，明确不采用 |

新增平台只需实现 `IMProvider` 适配器并注册，内核无需改动。

---

## 5. 安全约束（与内核一致，不绕过）

这是本模块的**安全红线**：IM 远程调用与本地调用走**同一条**安全链路：

1. **身份白名单**：仅白名单用户可触发执行；非白名单直接拒绝，不暴露内部信息。
2. **群 @ 触发**：群聊仅 @ 机器人时响应，防止误触与陌生人操控。
3. **高危操作确认**：删除/执行/不可逆写等高危操作，在 IM 内推送确认请求，确认后执行。
4. **审计追踪**：每次远程调用记录来源 `im:<platform>:<user_id>`，落 observability。
5. **会话隔离 + 熔断**：按 平台:用户/群 独立会话；单平台断线/异常熔断隔离，不拖垮主循环。

**反例（禁止）**：把 IM 消息直接映射到插件实现、跳过 permission/observability，等于给任何发消息的人开后门。

---

## 6. 接口设计（IMGateway）

```python
class IMGateway(Plugin):
    plugin_id = "im.gateway"

    def register(self, provider: IMProvider) -> None: ...
    def on_message(self, msg: Message) -> None: ...          # 入站：消息 → 会话事件 → loop
    def reply(self, session: Session, text: str) -> None: ...# 回推：内核结果 → 平台消息
    def approve(self, session: Session, prompt: str) -> bool: ...  # 高危操作 IM 内二次确认
```

```python
class IMProvider(Protocol):
    platform: str                            # telegram / discord / feishu / wechat_work ...
    def start(self, gateway: IMGateway) -> None: ...
    def send(self, session: Session, text: str) -> None: ...
    def identity(self, msg: Message) -> str: ...  # 返回 user_id，供白名单/审计
```

---

## 7. 与其他模块的关系

| 模块 | 关系 |
|---|---|
| loop / orchestration | 复用同一执行主轴，消息进入既有 loop |
| permission | 复用权限分级 + 确认门（高危操作 IM 内确认）|
| observability | 复用审计落盘，来源标注 im:* |
| constraints | 复用熔断/隔离，单平台故障不扩散 |
| skills / memory | 复用技能与分层记忆，会话上下文按平台隔离 |

---

## 8. ADR 索引

| ADR | 决策 |
|---|---|
| ADR-0018 | IMGateway 统一协议抽象，新增平台零侵入 |
| ADR-0019 | 分平台接入（Telegram/Discord Bot API、飞书 WebSocket、企业微信/公众号合规）|
| ADR-0020 | 安全约束（白名单 + 同一 invoke 链路 + 会话隔离）|
