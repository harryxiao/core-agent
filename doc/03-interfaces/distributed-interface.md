# 接口设计：分布式协作接口（Distributed Interface）

> 横切 ｜ 对应规格 `distributed/spec.md` ｜ 模块 `09-distributed/distributed.md`

---

## 1. A2AClient 接口

```python
class A2AClient:
    def read_card(self, peer: str) -> AgentCard: ...              # 读取对端 AgentCard
    def send_message(self, target: AgentCard, task: Task) -> TaskHandle: ...  # 委派任务
    def subscribe(self, handle: TaskHandle) -> Stream: ...        # 订阅进度（流式/推送）
```

- 作为 Client 委派任务给外部 Agent（Claude Code / Codex / Kilo 等），经对端 AgentCard 声明的接口发送任务。

## 2. A2AServer 接口

```python
class A2AServer:
    def expose(self) -> AgentCard: ...                  # 对外暴露 AgentCard
    def on_message(self, task: Task) -> TaskHandle: ... # 接收任务
    def report(self, handle: TaskHandle) -> None: ...   # 执行并回报结果
```

- 作为 Server 对外暴露能力被外部 Agent 调用；内部经 MCP 调用底层工具/数据完成任务，结果经 A2A 协议返回。

## 3. AgentCard 数据结构

```python
class AgentCard:
    provider: AgentProvider
    capabilities: list[AgentCapability]
    skills: list[AgentSkill]
    interface: AgentInterface
    signature: str | None    # 卡片签名，验证通过才接受身份与能力声明
```

## 4. 协议绑定与传输

- **默认/推荐**：JSON-RPC 2.0 over HTTP(S)，流式任务走 Server-Sent Events。
- **备选**：gRPC、HTTP+JSON/REST。
- **可选 P2P**：按公钥寻址、NAT 打洞直连优先、失败回退 relay、QUIC；仅传输层优化，不改上层 A2A 协议行为。
- `DistributedGateway` 负责拓扑接入与传输管理（HTTP(S) 默认 / gRPC / REST 备选）。

## 5. 安全鉴权

- **鉴权方案**：OAuth2 / mTLS / APIKey / OpenIdConnect；云端↔嵌入式敏感指令优先 mTLS 双向认证。
- **最小权限**：跨设备调用按最小权限 scope 授权，超出 scope 拒绝并审计（来源 `a2a:<peer>`）。
- **复用链路**：高危操作复用既有 permission 审批链路 + observability 审计落盘，不降安全等级。

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `A2A_PEER_UNREACHABLE` | 对等 Agent 不可达 |
| `A2A_CARD_INVALID` | AgentCard 解析失败或签名无效 |
| `A2A_PROTOCOL_UNSUPPORTED` | 对端声明的绑定不被支持 |
| `A2A_SCOPE_DENIED` | 调用超出已授权 scope |
| `A2A_AUTH_FAILED` | 鉴权失败（OAuth2/mTLS/APIKey） |
| `A2A_TASK_FAILED` | 委派任务执行失败 |

## 7. 关联

- 模块：`09-distributed/distributed.md`
- MCP 互补：`mcp-interface.md`（A2A Server 内部经 MCP 调用底层工具）
- 权限/审计链路：`permission-interface.md`、`observability-interface.md`
- 熔断隔离：`constraints-interface.md`
- 远端推理（可选）：`llm-provider-interface.md`
- 规格：`openspec/specs/distributed/spec.md`
- 变更：`openspec/changes/0009-distributed/`
