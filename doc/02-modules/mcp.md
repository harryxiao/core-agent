# 模块设计：MCP 集成（MCP Integration）

> 对应规格：`doc/openspec/specs/mcp/spec.md` ｜ 接口：`doc/03-interfaces/mcp-interface.md`

---

## 1. 模块定位

MCP（Model Context Protocol）集成让 CORE 以 **MCP client** 身份消费外部能力——
把外部 MCP server 的 **tools / resources / prompts** 统一纳入 L1 工具层与 L3 上下文，
**受与本地工具完全相同的约束**（可逆追踪 + 确认门 + coeffect 校验）。

---

## 2. 架构

```
L3 Loop ──► ToolProvider ──► [本地工具 | MCP 适配工具]
                                │
                     MCPClient ─┴─► MCP Server (stdio / HTTP)
                                       ├── tools
                                       ├── resources
                                       └── prompts
```

- **MCPClient**：负责发现（initialize/list_tools）、传输（stdio 子进程 / HTTP）、协议编解码。
- **MCP 适配器**：把远程 tool 包装成 `ToolDef`，符合四要素契约，注册进 PluginRegistry。

---

## 3. 关键设计

### 3.1 能力发现

- 启动/配置时 `initialize` + `list_tools` + `list_resources` + `list_prompts`。
- 发现的 tools 包装为 `mcp.<server>.<tool>` 命名空间的 `ToolDef`，进入注册表。

### 3.2 传输方式

| 传输 | 说明 | 适用 |
|---|---|---|
| **stdio** | 子进程标准输入输出 JSON-RPC | 本地、无网络暴露 |
| **HTTP/SSE** | 远程连接 | 跨机、云 MCP |

### 3.3 与本地工具同等的安全约束

| 约束 | MCP 工具的落地 |
|---|---|
| 可逆追踪 | 远程 tool 结果记入 EffectTracker；不可逆的标注并走确认门 |
| coeffect 校验 | 声明所需权限（如 `network:outbound`），缺失拒绝 |
| 确认门 | 远程写/删除/敏感操作先 `ask_user` |

### 3.4 resources 与 prompts 入上下文

- `resources` 作为只读上下文来源，纳入 Perceive 阶段的预算裁剪。
- `prompts` 作为可选的推理模板，供 Reason 阶段选用。

---

## 4. 错误处理

| 场景 | 行为 |
|---|---|
| server 连接失败 | 标记该 server 为 `DEGRADED`，不阻塞其他工具 |
| 协议/版本不兼容 | 降级尝试，失败则记录并跳过 |
| 远程工具超时 | 按 timeout 中止，返回 `REMOTE_TIMEOUT` |
| 远程不可逆操作 | 强制确认门，拒绝则改写 |

---

## 5. 关联

- 规格：`doc/openspec/specs/mcp/spec.md`
- 工具层：`doc/02-modules/tool-use.md`
- 接口：`doc/03-interfaces/mcp-interface.md`
- 测试：`doc/04-testing/test-cases.md`（MCP 系列）
