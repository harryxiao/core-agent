# tasks — MCP Server 模式 stdio 事件循环（change 0073）

## 1. 测试先行（红）
- [x] 1.1 `tests/test_mcp_server_stdio.py` 新建：事件循环面（按 id 应答 / 通知不应答 / 非法行跳过 / EOF 退出）
- [x] 1.2 异常隔离：未知方法 `-32601` 后循环继续；工具提供者抛错 → 错误应答且循环继续
- [x] 1.3 暴露面：`core.` 前缀 / 白名单（裸名与带前缀两种写法）/ 未暴露调用 `PERMISSION_DENIED` / 禁二级代理
- [x] 1.4 CLI 面：`--whitelist` CSV 解析；非 stdio 传输拒绝
- [x] 1.5 端到端：本仓 `MCPClient` 子进程拉起 `mcp serve` → 握手 / 发现 / 调用（真读文件）/ 越权拒绝
- [x] 1.6 红证：实现前先跑，确认失败面（`ImportError: PROTOCOL_VERSION` 等）

## 2. 实现（绿）
- [x] 2.1 `models.py`：`PROTOCOL_VERSION` 共享常量；`client.py` 改用之；`__init__.py` 导出
- [x] 2.2 `server.py`：`_bare_name` / `_as_params` / `_error` 归一辅助 + 白名单前缀归一
- [x] 2.3 `server.py`：`list_tools` 加 `core.` 前缀 + 过滤 `mcp.*`；`call_tool` 只接受已暴露名
- [x] 2.4 `server.py`：`serve_stdio` + `_respond` / `_dispatch` / `_serialize_call` / `_encode`；`serve` 委托 `_bind`
- [x] 2.5 `entry.py`：`mcp serve --whitelist` + `_mcp` / `_mcp_serve` / `_mcp_whitelist` + `_HANDLERS` 注册
- [x] 2.6 `tests/test_mcp.py` server 单测对齐 `core.` 命名空间契约
- [x] 2.7 绿证：全量 pytest 通过（900 例）

## 3. 规格
- [x] 3.1 `mcp` spec delta：MODIFIED「MCP Server 模式」（stdio 事件循环 / 握手 / 通知 / 异常隔离 / 未知方法 / EOF）
- [x] 3.2 `mcp` spec delta：MODIFIED「工具暴露与白名单」（`core.` 前缀 / 只接受已暴露名 / 禁二级代理 / `--whitelist`）
- [x] 3.3 新增场景：stdio 事件循环按 id 应答 / 请求异常不终止事件循环 / 工具命名空间隔离 / 远程工具不被二级代理暴露
- [x] 3.4 `openspec validate 0073-mcp-server-stdio-loop` 通过

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/mcp-interface.md` §6：`serve_stdio` / `core.<tool>` / 事件循环与错误分层
- [x] 4.2 `doc/02-modules/mcp.md` §3.5：server 侧事件循环与暴露面契约
- [x] 4.3 `doc/07-mcp-server/mcp-server.md`：状态从「待接入」改为 stdio 已接入（HTTP 待接入）
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0070 + 映射表行
- [x] 4.5 `doc/04-testing/test-cases.md`：TC-MCP-07/08/09

## 5. 归档与账本
- [x] 5.1 手动归档：合并 delta 进 `doc/openspec/specs/mcp/spec.md`，变更目录移入 `archive/2026-10-05-0073-mcp-server-stdio-loop/`
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 `coding-plan/phase-19.md`：B3 行标关闭（附 change id）；§6 B3 段替换为已关闭块；登记新行（标准 MCP envelope 未对齐 / 默认暴露面粗粒度）
- [x] 5.4 `coding-plan/README.md` 计数与单元格更新
- [x] 5.5 四门复跑 + 记忆更新 + 提交
