# design — MCP 标准 envelope 双向对齐（change 0075）

## 一手实测（决定设计的事实）

对本机 `claude mcp serve` 发**标准** `initialize` + `tools/list` + `tools/call` 探测：

```json
{"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{"listChanged":true}},
           "serverInfo":{"name":"claude/tengu","version":"2.1.283"}},"id":1}
{"result":{"tools":[{"name":"Agent","searchHint":..., "aliases":[...], ...},{"name":"Read",...}]},"id":2}
{"result":{"content":[{"type":"text","text":"{\"type\":\"text\",\"file\":{...}}"}]},"id":3}   // 成功，无 isError 键
{"error":{"code":-32603,"message":"Tool no_such_tool not found"},"id":4}                      // 未知工具 → 协议层错误
```

四条结论直接锁定设计：

1. **协议版本同源**：`claude mcp serve` 应答 `2024-11-05` —— 与本端 `PROTOCOL_VERSION` 逐字相同
   ⇒ 现有「严格比对不匹配即 `MCP_PROTOCOL_MISMATCH`」**无需放宽**（放宽反而丢掉既有测试的语义）。
2. **`tools/list` 标准容器键** + tool 对象带 **12 个非标准扩展字段**（`aliases` / `searchHint` /
   `backgrounding` / `maxResultSizeChars` …） ⇒ `RemoteTool(**item)` 双错：遇容器键会逐字符迭代、
   遇扩展字段会 `TypeError`。**必须投影已知键**。
3. **`tools/call` 成功应答无 `isError` 键**（缺省而非 `false`） ⇒ 判定用 `raw.get("isError")` 真值性，
   **不可**用 `"isError" in raw`。
4. **未知工具走 JSON-RPC 错误**（协议层），非 `isError` 结果 ⇒ 本端 `_await` 已把它包成
   `MCPError(MCP_UNAVAILABLE)`，`call_tool` 隔离为 `CallResult(ok=False, code=MCP_UNAVAILABLE)`。
   这是**可接受的现状**（错误码映射粒度不足转出为账本新行，见下）。

## 决策

### D1 标准信封只用 `content[].text`，不用 `structuredContent`
协议版本是 `2024-11-05`，`structuredContent` 属 `2025-06-18` ⇒ 引入即为**版本越界**。
故：**载荷一律 JSON 编码进 `text`**，「是不是错」由 `isError` 承载。

- 成功：`text = json.dumps(<工具数据>, ensure_ascii=False)`（**总是**编码，即使数据已是 str
  —— 保证 client 侧「解码即还原」的往返保真；不编码则 `"123"` 之类会被解码成 int 而漂移）。
- 失败：`text = json.dumps({"code": ..., "error": ...}, ensure_ascii=False)`。

这使得**本仓自环**（自己 client 挂自己 server）语义干净：wire 只承载**载荷**与 `isError`，
client 侧不再出现「`CallResult` 套 `CallResult`」的双层包装。

### D2 client 侧解析：标准优先，裸形状兜底
一个 `_unwrap(raw, key)` + 一个 `_project`（只取已知键）覆盖三处发现接口；
`call_tool` 一个 `_parse_call_result(raw)`：

```
标准信封（dict 且含 content/isError）→ 结构化归一
其余（裸列表 / 裸对象 / 旧形状）      → 原样承载为 data（向后兼容，不抛）
```

**为什么保留兜底**：仓内 echo server（两个测试夹具）仍是裸形状 —— 它们正好成为
「旧服务端不挂（onboarding）不被打破」的**真实子进程回归样本**，比新造夹具更有说服力。

### D3 `FakeTransport` 改为标准形状
它是「远端」的模型而非本仓约定的一部分；继续吐旧形状就等于**测试替身与真实世界不一致**。
其 `tools/call` 吐 `{"content":[{"type":"text","text": json.dumps({"result": f"ok:{name}", "args": ...})}]}`
⇒ 既有断言 `result.data["result"] == "ok:search"` **原样通过**（解码即还原）。

### D4 命名不放宽
对外名仍 `core.<tool_id>`（规格「工具命名空间隔离」明文要求）。真机验收若因点号被拒，
**另立裁决改规格**，不在本变更加戏（避免「先验改名 → 规格与实现再度漂移」）。

### D5 兼容性代价评估
- 破坏面：**只有** `MCPClient` 的解析口径与 `MCPServer` 的应答形状；Python 侧窄接口
  （`MCPServer.call_tool` 的领域返回仍是 `CallResult`）**不动** ⇒ `test_mcp.py` 的领域断言零改动。
- 无持久化影响（wire 不落盘）；无配置影响。

## 放弃的方案

- **A：server 侧同时吐新旧两种信封**（按客户端能力协商）—— 无协商机制（`initialize` 无此字段），
  且「两套形状共存」正是本账本行要消灭的东西。
- **B：client 侧只认标准、删掉裸形状兜底** ⇒ 两个真实 echo 夹具子进程立即失效，
  失去「旧服务端兼容」的真实回归样本。
- **C：协议版本升到 `2025-06-18` 以启用 `structuredContent`** —— 越界且无收益（`text` 已够）。

## 转出（新增账本行，不在本变更内）

- **远端 JSON-RPC 错误码未映射**：`StdioTransport._await` 把一切远端 `error` 包成
  `MCP_UNAVAILABLE` ⇒ 对端「工具不存在」（`-32603`/`-32602`）在本端表现为 `MCP_UNAVAILABLE`
  而非 `MCP_TOOL_NOT_FOUND`（粒度不足，不误导但不够精确）。
