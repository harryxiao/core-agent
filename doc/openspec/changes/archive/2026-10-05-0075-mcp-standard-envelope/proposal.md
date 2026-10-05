# MCP 标准 envelope 双向对齐（mcp-standard-envelope）

## Why

账本 **B6**（`mcp` wire envelope 未对齐标准）。规格「MCP Server 模式」逐字列出外部客户端
（**Claude Code、Cursor**）可直接挂载本 server —— 而一手核实：本仓 `tools/list` 应答为**裸列表**、
`tools/call` 应答为**序列化 `CallResult` 直出**（change `0054` 确立的仓内三方约定：client /
`FakeTransport` / echo server），**非**标准 MCP envelope。后果是**双向都不可互操作**：

| 方向 | 现状 | 实测证据 |
|---|---|---|
| 被外部挂载（server 向） | 第三方客户端无法解析本 server 的 `tools/list` / `tools/call` | 标准客户端要求 `{"tools": [...]}` / `{"content": [...], "isError": ...}` |
| 主动挂载（client 向） | 本 client 挂不上任何标准 MCP server | `core-agent mcp add "claude mcp serve" --name cc` 实测失败：`-32603` 列出缺失的 `params.protocolVersion` / `capabilities` / `clientInfo`（本端 `initialize` params **为空**）；且 `RemoteTool(**item)` 遇标准应答的**未知厂商字段**（Claude Code 的 tool 对象带 12 个扩展键）会 `TypeError`，遇 `{"tools":[...]}` 容器键会逐字符迭代报错 |

即：**「MCP Server 模式」规格场景「stdio 本地挂载」字面点名的两个客户端，在生产一个也挂不上**。
这不是可选的对齐，而是该场景成立与否的硬前置（与 E12 / E11② / B3 / B4 同型 —— **规格要求 X 而实现没有** ⇒
改代码向规格靠拢）。

## What Changes

- `src/core/mcp/server.py`
  - `tools/list` 应答 → `{"tools": [asdict(tool) ...]}`（标准容器键）。
  - `tools/call` 应答 → 标准信封：成功 `{"content": [{"type": "text", "text": <JSON 载荷>}], "isError": false}`；
    失败 `{"content": [{"type": "text", "text": {"code": ..., "error": ...}}], "isError": true}`。
  - `initialize` / `ping` 不变（已是标准形状）。
- `src/core/mcp/client.py`
  - `initialize` 请求携带标准三元组 `protocolVersion` / `capabilities` / `clientInfo`（不再空 params）；
    应答版本比对口径不变（**实测 Claude Code 应答 `2024-11-05`，与本端同源**，严格比对即正确）。
  - `list_tools` / `list_resources` / `list_prompts`：解析标准容器键，**只取已知字段**（容忍厂商扩展键），
    并**向后兼容**裸列表应答（既有 echo server / 替身不被打破）。
  - `call_tool`：把标准结果信封（`content` + `isError`）归一为本地 `CallResult`。
- `src/core/mcp/transport.py`：`FakeTransport` 改为产出**标准**应答（它是「远端」的模型）。
- 规格 delta：`mcp` spec **ADDED**「标准 MCP 互操作（双向）」。
- 文档：接口 §6 的「已知偏离」改为「已对齐」并补标准形状；模块 §4；ADR-0072；方案文档 §9 P4 销项。

## Non-goals

- **不**改对外工具命名（仍 `core.<tool_id>`）：命名空间隔离是本仓规格明文要求
  （「工具暴露与白名单」场景「工具命名空间隔离」）；能否被第三方接受由**真机验收**判定，
  真机若因命名被拒，另立裁决（不在本变更内先验性地改名）。
- **不**实现 `resources/list` / `prompts/list` 的 server 侧应答（本 server 只声明 tools 能力）。
- **不**引入 `structuredContent` / `nextCursor`（`2025-06-18` 特性，本端协议版本为 `2024-11-05`）。
- **不**统一远端 JSON-RPC 错误码到本地错误码（如把远端 `-32603` 映射为 `MCP_TOOL_NOT_FOUND`）——
  属独立问题（转出为账本新行）。
- **不**碰 B7（默认暴露面启发式），本变更只对齐 wire 形状。

## 风险

- **仓内三方约定被打破**：client / `FakeTransport` / echo server 三处需同步改。缓解：
  client 侧**保留裸列表与裸对象的后向解析**，旧形状 fixture 不作废（既有用例即为兼容性回归）。
- **第三方客户端接受度不可纸面断定**：以**真机双向验收**（`claude mcp add` 挂载本 server +
  本 client 挂载 `claude mcp serve` 并真调一个工具）作为关闭证据，而非仅靠单测。
