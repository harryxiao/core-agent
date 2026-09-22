# 模块设计：MCP 集成（MCP Integration）

> 对应规格：`doc/openspec/specs/mcp/spec.md` ｜ 接口：`doc/03-interfaces/mcp-interface.md`

---

## 1. 模块定位

MCP（Model Context Protocol）集成让 CORE 具备**双向** MCP 能力：

- **client 方向（吃）**：消费外部 MCP server 的 **tools / resources / prompts**，统一纳入 L1 工具层与 L3 上下文，
  **受与本地工具完全相同的约束**（可逆追踪 + 确认门 + coeffect 校验）。
- **server 方向（被吃）**：以 MCP server 身份对外暴露 L1 原子工具与技能，供外部 Agent（Claude Code / Cursor / Kiro 等）
  挂载复用，形成「机器 → core-agent」入口，与 UI 三入口（CLI/Web/Desktop，见 `06-ui-frontend/ui-architecture.md`）对称；
  暴露面受白名单约束，调用走与本地一致的 permission/observability 安全链路，能力复用但安全不下放。

---

## 2. 架构

```
【client 方向：吃】
L3 Loop ──► ToolProvider ──► [本地工具 | MCP 适配工具]
                                │
                     MCPClient ─┴─► 外部 MCP Server (stdio / HTTP)
                                       ├── tools
                                       ├── resources
                                       └── prompts

【server 方向：被吃】
外部 Agent (Claude Code / Cursor) ──► MCPServer ──► 白名单 ──► ToolProvider（同一内核）
```

- **MCPClient**：负责发现（initialize/list_tools）、传输（stdio 子进程 / HTTP）、协议编解码。
- **MCP 适配器**：把远程 tool 包装成 `ToolDef`，符合四要素契约，注册进 PluginRegistry。
- **MCPServer**：负责握手（initialize/list_tools/call_tool）、传输（stdio / Streamable HTTP）、把本地工具经白名单包装为 MCP tool。

---

## 3. 关键设计

### 3.1 能力发现（client）

- 启动/配置时 `initialize` + `list_tools` + `list_resources` + `list_prompts`。
- 发现的 tools 包装为 `mcp.<server>.<tool>` 命名空间的 `ToolDef`，进入注册表。

### 3.2 传输方式

| 传输 | 说明 | 适用 |
|---|---|---|
| **stdio** | 子进程标准输入输出 JSON-RPC | 本地、无网络暴露 |
| **Streamable HTTP** | 远程连接，单连接多会话复用（Mcp-Session-Id） | 跨机、云 MCP |

### 3.3 与本地工具同等的安全约束

| 约束 | MCP 工具的落地 |
|---|---|
| 可逆追踪 | 远程 tool 结果记入 EffectTracker；不可逆的标注并走确认门 |
| coeffect 校验 | 声明所需权限（如 `network:outbound`），缺失拒绝 |
| 确认门 | 远程写/删除/敏感操作先 `ask_user` |

### 3.4 resources 与 prompts 入上下文

- `resources` 作为只读上下文来源，纳入 Perceive 阶段的预算裁剪。
- `prompts` 作为可选的推理模板，供 Reason 阶段选用。

### 3.5 MCP Server 模式（对外工具源）

- **暴露面复用 ToolProvider**：不复制工具实现，经白名单从 ToolProvider/PluginRegistry 挑选并包装为 MCP tool，
  命名空间 `core.<tool>`，与本地 `mcp.<server>.<tool>` 隔离。
- **默认最小暴露**：未配置白名单时仅暴露只读类工具；写/删除/敏感工具默认不暴露。
- **安全约束透传**：外部调用走同一 invoke 链路（permission 确认门 + observability 审计），来源标注 `external:<client_id>`。
- **会话隔离**：每个 MCP 连接独立 session，单连接熔断隔离不拖垮主循环。
- **会话多流复用**：单一 HTTP(TCP) 连接经 Mcp-Session-Id 会话标识承载多个会话，会话与连接解耦，请求按 Session-Id 分流互不串扰。
- **禁止二级代理**：初版不把 MCP client 已发现的远程工具再转暴露，防 A 挂 B、B 挂 A 的无限代理。

---

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| server 连接失败 | 标记该 server 为 `DEGRADED`，不阻塞其他工具 |
| 协议/版本不兼容 | 降级尝试，失败则记录并跳过 |
| 远程工具超时 | 按 timeout 中止，返回 `REMOTE_TIMEOUT` |
| 远程不可逆操作 | 强制确认门，拒绝则改写 |
| 外部未授权调用 | 返回 `PERMISSION_DENIED`，不执行 |
| 外部高危操作 | 强制确认门 + 审计（来源 external） |
| 外部连接异常/崩溃 | 熔断该连接，不影响其他客户端 |

---

## 5. 关联

- 规格：`doc/openspec/specs/mcp/spec.md`
- 工具层：`doc/02-modules/tool-use.md`
- 接口：`doc/03-interfaces/mcp-interface.md`
- MCP Server 模式方案：`doc/07-mcp-server/mcp-server.md`
- 横切：`02-modules/permission.md` / `02-modules/observability.md`
- 测试：`doc/04-testing/test-cases.md`（MCP 系列）
