# 接口设计：IM 网关接口（IM Interface）

> 横切 ｜ 对应规格 `im/spec.md` ｜ 模块 `08-im-gateway/im-gateway.md`

---

## 1. IMGateway 接口

```python
class IMGateway(Plugin):
    plugin_id = "im.gateway"

    def register(self, provider: IMProvider) -> None: ...
    def on_message(self, msg: Message) -> None: ...
    def reply(self, session: Session, text: str) -> None: ...
    def approve(self, session: Session, prompt: str) -> bool: ...
```

- `register`：注册平台 Provider 适配器，新增平台零侵入（内核 loop、工具链、记忆与权限链路无需改动）。
- `on_message`：入站消息统一映射为会话事件进入内核 loop 执行（消息驱动会话）。
- `reply`：内核执行结果经 Provider 编码回推到来源会话。
- `approve`：高危操作（删除/执行/不可逆写）在 IM 内推送确认请求，确认后执行。

## 2. Message 事件模型

```python
class Message:
    platform: str      # telegram / discord / feishu / wechat_work ...
    user_id: str       # 平台用户标识，供白名单与审计
    text: str
    is_group: bool     # 群聊标记（群内仅 @ 机器人时响应）
    session_key: str   # 平台:用户/群 会话隔离键
```

## 3. IMProvider 适配器接口

```python
class IMProvider(Protocol):
    platform: str
    def start(self, gateway: IMGateway) -> None: ...
    def send(self, session: Session, text: str) -> None: ...
    def identity(self, msg: Message) -> str: ...   # 返回 user_id，供白名单/审计
```

- 官方通道接入：Telegram/Discord 用官方 Bot API（webhook/长轮询）、飞书用开放平台长连接 WebSocket（事件订阅）、微信用企业微信/公众号合规通道；个人号接入因封号风险不采用。

## 4. 调用流程

1. Provider 收消息 → 构造 `Message`
2. `IMGateway.on_message` → `identity` 身份鉴权 + 白名单校验
3. 入站消息进入内核 loop，复用 `tool-use-interface` 的 invoke 链路
4. 高危操作 → `approve` IM 内二次确认
5. 执行结果 → `reply` 回推来源会话，审计来源 `im:<platform>:<user_id>`

## 5. 身份鉴权与安全约束

- **身份白名单**：仅白名单用户可触发执行；非白名单拒绝且不暴露内部信息。
- **群 @ 触发**：群聊仅 @ 机器人时响应，防止误触与陌生人操控。
- **安全链路**：IM 远程调用与本地调用走同一条 permission/observability 链路，不绕过。
- **会话隔离 + 熔断**：按 `平台:用户/群` 独立会话，单平台断线/异常熔断隔离，不拖垮主循环。

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `IM_PLATFORM_UNSUPPORTED` | 平台无对应 Provider 适配器 |
| `IM_NOT_WHITELISTED` | 非白名单用户，拒绝执行 |
| `IM_CONFIRM_DENIED` | 高危操作确认被拒绝 |
| `IM_CONFIRM_TIMEOUT` | 高危操作确认超时 |
| `IM_PLATFORM_DISCONNECTED` | 平台连接断开（触发熔断隔离） |
| `IM_SEND_FAILED` | 回推消息发送失败 |

## 7. 关联

- 模块：`08-im-gateway/im-gateway.md`
- 工具契约：`tool-use-interface.md`
- 权限/审计链路：`permission-interface.md`、`observability-interface.md`
- 熔断隔离：`constraints-interface.md`
- 规格：`openspec/specs/im/spec.md`
- 变更：`openspec/changes/0005-im-gateway/`
