# MCP Server 模式：让 core-agent 成为外部 Agent 的工具源

> 对应规格：`doc/openspec/specs/mcp/spec.md`（server 侧 Requirement）｜ 接口：`doc/03-interfaces/mcp-interface.md`
> 本方案文档对应 ADR-0016 ~ 0017，变更提案见 `doc/openspec/changes/0004-mcp-server/`

---

## 1. 定位与场景

core-agent 目前已有三类「**人 → core-agent**」入口（CLI / Web / Desktop，见 `06-ui-frontend/ui-architecture.md`），
并作为 **MCP client** 消费外部能力（`02-modules/mcp.md`）。本模块补齐反向入口「**机器 → core-agent**」：

> **MCP Server 模式**：让 core-agent 以 MCP server 身份，把自身的 L1 原子工具与技能作为标准 MCP tools
> 对外暴露，供任何兼容 MCP client 的外部 Agent（Claude Code / Cursor / Kiro / 其他 harness）挂载复用。

典型场景：

| 场景 | 说明 |
|---|---|
| 多 Agent 协作 | 一个「主控 Agent」通过 MCP 挂载 core-agent，把文件读写、Web 操作、记忆查询等原子能力作为工具调用 |
| 复用已验证能力 | core-agent 内已沉淀的可逆插件与技能，被第三方工具链直接消费，避免重复实现 |
| 统一安全边界 | 外部 Agent 无法绕过 core-agent 的权限/审计/熔断约束，能力复用但安全不下放 |

---

## 2. 与 MCP client 的对称关系

MCP 是**双向协议**。core-agent 在同一套 `mcp` capability 下同时扮演两个对称角色：

| 维度 | MCP client（已有） | MCP server（本模块新增） |
|---|---|---|
| 方向 | 消费外部 tools/resources/prompts | 对外暴露自身 tools/skills |
| 命名空间 | 远程工具映射进本地 `mcp.*` | 自身工具以 `core.<tool>` 暴露 |
| 安全 | 远程工具受本地同等约束 | 外部调用走内核 permission/observability |
| 传输 | 连接外部 stdio/HTTP server | 自身作为 stdio/HTTP(SSE) server 被挂载 |

同一内核、同一 ToolProvider、同一安全链路，仅传输方向相反。

---

## 3. 架构

```
                     ┌──────────────────────────────────────────────┐
  外部 Agent        │                 core-agent 内核               │
 (Claude Code/      │                                              │
  Cursor/Kiro)      │   ┌───────────────┐   ┌───────────────────┐  │
      │             │   │ MCPServer     │──▶│ ToolProvider      │  │
      │ MCP         │   │ (stdio/HTTP)  │   │ (L1 原子工具+技能)│  │
      ├─ tools ────▶│   └──────┬────────┘   └─────────┬─────────┘  │
      │   call_tool │          │ 白名单/命名空间        │ invoke     │
      │             │          ▼                       ▼            │
      │             │   ┌───────────────────────────────────────┐   │
      │             │   │       统一调用链路（不绕过内核）          │   │
      │             │   │  permission 确认门 → constraints 熔断   │   │
      │             │   │  → observability 审计(来源=外部客户端)   │   │
      │             │   └───────────────────────────────────────┘   │
      └─────────────┘                                              │
                    └──────────────────────────────────────────────┘
```

**核心原则**：MCP server 只是**入口适配层**，不是新内核。它把外部 `call_tool` 请求翻译成与本地调用
完全相同的 `invoke`，经过 permission / observability / constraints 三道横切关卡后执行，EffectTracker
记录来源为外部客户端（`source=external:<client_id>`）。

---

## 4. 暴露面与白名单

对外暴露**不是**把全部 L1 工具直接开放，而是经过白名单筛选的最小暴露：

- **默认最小暴露**：仅暴露只读类工具（如文件读取、Web 查询、记忆检索）；写、删除、执行、敏感操作默认**不暴露**。
- **显式白名单**：通过配置显式开放具体工具/技能；未列入白名单的一律不可见（`list_tools` 不返回）。
- **命名空间隔离**：对外工具名为 `core.<tool_id>`，与本地工具名、`mcp.*` 远程工具名天然隔离，避免递归挂载冲突。
- **二级代理禁止**：初版**不**把自身 MCP client 已发现的远程工具再转暴露（防止 A 挂 B、B 挂 A 的无限代理）。

---

## 5. 传输方式

| 传输 | 适用 | 特点 |
|---|---|---|
| **stdio**（默认） | 本地单客户端（Claude Code 直接 `command` 拉起） | 零配置、零网络暴露、进程内 JSON-RPC |
| **HTTP / SSE**（可选） | 远程、多客户端 | 需鉴权（token/mTLS），SSE 流式返回 |

`MCPEndpoint` 已有 `stdio | http` 两种形态（`03-interfaces/mcp-interface.md`），server 侧复用同一结构：
stdio 走子进程标准输入输出，HTTP 走 `POST /mcp`（JSON-RPC）+ `GET /sse`（流式）。

---

## 6. 安全约束（与内核一致，不绕过）

这是本模块的**安全红线**：外部 Agent 通过 MCP 调用，与本地模型调用走**同一条**安全链路：

1. **权限分级 + 确认门**：高危操作（删除、执行、不可逆写）触发人工审批；`permission` 判定来源为外部客户端。
2. **审计追踪**：每次外部调用记录 `client_id + tool + 参数摘要 + 结果 + 是否需审批`，落 `observability`。
3. **熔断隔离**：单客户端异常/超时熔断该连接，不影响主循环与其他客户端（复用 `constraints` 熔断）。
4. **鉴权**（HTTP/SSE）：token/mTLS 必选，未鉴权连接直接拒绝；stdio 依赖进程边界，默认信任本机拉起方。

**反例（禁止）**：把外部调用直接映射到插件实现、跳过 permission/observability，等于给外部 Agent 开后门。

---

## 7. 接口设计（MCPServer）

```python
class MCPServer(Plugin):
    plugin_id = "mcp.server"

    def serve(self, transport: MCPEndpoint, allowlist: Allowlist) -> Server: ...
    def list_tools(self, conn: ClientConn) -> list[ToolDef]: ...   # 白名单过滤后返回
    def call_tool(self, conn: ClientConn, name: str, args: dict) -> ToolResult: ...
    # 内部：call_tool → ToolProvider.invoke（带 source=external:client_id）
```

新增错误码（server 侧，复用现有错误码体系）：

| code | 含义 |
|---|---|
| `MCP_NOT_EXPOSED` | 工具未在白名单内，不可见/不可调 |
| `PERMISSION_DENIED` | 越权调用（复用 permission） |
| `MCP_AUTH_FAILED` | HTTP/SSE 鉴权失败 |
| `MCP_CLIENT_FAULT` | 客户端异常，触发熔断 |

---

## 8. 关键技术决策（ADR 摘要）

- **ADR-0016**：暴露面复用 ToolProvider + 白名单，不复制工具实现、不绕过内核安全。
- **ADR-0017**：传输 stdio 优先（本地零配置）+ HTTP/SSE 可选（远程多客户端，鉴权必选）。

完整决策记录见 `doc/01-architecture/adr.md`。

---

## 9. 分阶段落地

| 阶段 | 内容 | 状态 |
|---|---|---|
| P1 | MCP server 骨架 + stdio transport + `core-agent mcp-serve` 入口 | **已落地**（change `0073`：`mcp serve` 以 stdio 事件循环对外提供工具） |
| P2 | 暴露面白名单 + 权限透传 + 审计来源标注 | **已落地**（change `0073` 接线后生产可达：白名单 / `core.` 命名空间 / 禁二级代理 / `external:<client_id>`） |
| P3 | HTTP/SSE transport + 鉴权 + 多客户端会话隔离 | 待开发（`mcp serve --transport http` 明确拒绝） |
| P4 | 打包可执行入口 + Claude Code/Cursor 接入模板 + 端到端用例 | 部分（端到端已有：`tests/test_mcp_server_stdio.py` 用本仓 client 拉起真实子进程）；**标准 MCP envelope 未对齐**，第三方客户端直接挂载待办 |

---

## 10. 风险与权衡

| 风险 | 对冲 |
|---|---|
| 暴露面越权 | 默认最小暴露（只读），写/删/执行需显式白名单 + 确认门 |
| HTTP/SSE 开洞 | 鉴权必选（token/mTLS），未鉴权拒绝；默认只开 stdio |
| 二级代理递归 | 初版禁止转暴露远程工具 |
| 外部调用拖垮内核 | 会话隔离 + 熔断 + 调用预算（constraints） |

---

## 11. 关联文档

- 规格：`doc/openspec/specs/mcp/spec.md`（client + server 双侧 Requirement）
- 变更：`doc/openspec/changes/0004-mcp-server/`（proposal / design / tasks / delta）
- 模块：`doc/02-modules/mcp.md`（client 视角 + server 方向）
- 接口：`doc/03-interfaces/mcp-interface.md`（MCPClient + MCPServer）
- 入口对称：`doc/06-ui-frontend/ui-architecture.md`（人 → core-agent 三入口）
- 横切：`02-modules/permission.md` / `02-modules/observability.md` / `02-modules/constraints.md`
- ADR：`doc/01-architecture/adr.md`（ADR-0016 ~ 0017）
