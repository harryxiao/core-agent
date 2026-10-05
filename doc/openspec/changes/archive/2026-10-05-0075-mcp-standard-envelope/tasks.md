# tasks — MCP 标准 envelope 双向对齐（change 0075）

## 1. 测试先行（红）
- [x] 1.1 `tests/test_mcp_standard_envelope.py` 新建：client `initialize` 携带标准三元组；
      `tools/list` 标准容器键 + **厂商扩展字段被忽略**；裸列表仍可解析
- [x] 1.2 client `tools/call` 归一：成功 → `ok/data`（JSON 文本解码）；`isError` → `ok=False`
      （文本为 `{"code","error"}` 时还原结构化错误码；纯文本原样承载）
- [x] 1.3 server `tools/list` wire = `{"tools": [...]}`；`tools/call` wire = `content`/`isError`
      （成功 + 未授权两例）
- [x] 1.4 自环（server 的**真实应答帧**喂回 client）：成功调用与未授权调用各自往返保真
- [x] 1.5 红证：实现前跑 **12 failed / 3 passed** —— 失败面即两处根因：client 因容器键/扩展字段
      解析错（`RemoteTool(**item)`）、`initialize` 空 params；server 侧 `tools/list` 为裸列表、
      `tools/call` 直出 `CallResult`。3 个先绿的是「裸列表仍可解析」「旧式调用形状仍可承载」
      「`initialize` 应答本已标准」

## 2. 实现（绿）
- [x] 2.1 `src/core/mcp/server.py`：`_dispatch("tools/list")` → 容器键；`_serialize_call` → 标准信封
      （新增 `_envelope(payload, is_error)`，载荷**总是** JSON 编码以保证解码即还原）
- [x] 2.2 `src/core/mcp/client.py`：`_handshake()` 标准三元组；`_unwrap`（容器键/裸列表双认）+
      只取已知键的投影（容忍厂商扩展字段）；`_parse_call_result` 归一标准信封
- [x] 2.3 `src/core/mcp/transport.py`：`FakeTransport` 产出标准应答（它是「远端」的模型）
- [x] 2.4 更新既有 wire 断言（`tests/test_mcp_server_stdio.py` 四处暴露面 + 一处拒绝 + 一处端到端）；
      两处 echo 夹具**保留裸形状**，成为「旧服务端不挂」的真实子进程回归样本
- [x] 2.5 绿证：全量 pytest **936 passed**（基线 921）；四门全绿（ruff check / ruff format / pyright 0 error）

## 3. 规格
- [x] 3.1 `mcp` spec delta：ADDED「标准 MCP 互操作（双向）」+ 7 场景
- [x] 3.2 `openspec validate 0075-mcp-standard-envelope` 通过

## 4. 真机双向验收（一手证据）
- [x] 4.1 **反向（本 client 挂标准 server）**：`core-agent mcp add "claude mcp serve" --name cc`
      成功 —— 原为 `MCP_UNAVAILABLE: 远端错误: -32603 [params.protocolVersion/capabilities/clientInfo]`，
      现输出「已安装 MCP 端点: cc」并列出对端 **20 个**工具（`mcp.cc.Agent` … `mcp.cc.ScheduleWakeup`）
- [x] 4.2 **被挂载（标准 client 挂本 server）**：`claude mcp add ... -- <本仓> core-agent mcp serve`
      后 `claude mcp list` 报 **`✔ Connected`**（Claude Code 完成 initialize + tools/list 并逐字段校验通过）；
      此前该形状会被拒
- [x] 4.3 证据记录：本文件 §4.1/§4.2 + 账本 B6 关闭块；临时端点/项目注册与 `~/.claude.json`
      残留条目已清理（`claude mcp remove` + 删除临时项目项）

## 5. 文档
- [x] 5.1 `doc/03-interfaces/mcp-interface.md`：§6「已知偏离」→「配置面契约（已对齐标准）」+ §5 后补标准形状
- [x] 5.2 `doc/02-modules/mcp.md` §4：wire 形状行由「已知偏离」改为标准
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0072 + 变更追踪行；ADR-0070 尾部「⚠️ 已知偏离」加指向
- [x] 5.4 `doc/07-mcp-server/mcp-server.md` §9 P4 销项（标准 envelope 已对齐 + 真机挂载证据）
- [x] 5.5 `doc/04-testing/test-cases.md`：TC-MCP-11

## 6. 收口
- [x] 6.1 `coding-plan/phase-19.md`：§1 表 B6 行、§0 结论、§4 B6 段（→ 已关闭块）、§9 第 5 项、计数
- [x] 6.2 `coding-plan/README.md`：行 49 / 82 同步
- [x] 6.3 手动归档（合并 delta + 移动目录）+ `openspec validate --all` 全绿
- [x] 6.4 记忆更新 + 提交
