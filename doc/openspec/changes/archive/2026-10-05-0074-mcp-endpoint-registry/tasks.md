# tasks — MCP 端点注册表与 CLI 接线（change 0074）

## 1. 测试先行（红）
- [x] 1.1 `tests/test_mcp_endpoints.py` 新建：注册表落盘/读回/删除、原子写、损坏与残缺条目降级告警
- [x] 1.2 名称派生（URL → 主机名 / 命令行 → 基名 / `--name` 覆盖）+ 重名拒绝
- [x] 1.3 稳定命名：同名安装两次（两个 client 实例）工具名一致 `mcp.<名>.<工具>`
- [x] 1.4 装配期注册：临时 `CORE_STATE_DIR` 预置真 stdio 端点（stdlib echo server）⇒
      `build_runtime` 后工具集含 `mcp.<名>.echo`
- [x] 1.5 装配期降级：预置不可达端点 + 可达端点 ⇒ 装配成功、告警、可达者仍注册
- [x] 1.6 CLI 端到端（子进程）：`mcp add` → `mcp list` 列出 → `mcp remove` 摘除；连不上不落盘
- [x] 1.7 红证：实现前跑，记录失败面 —— 红灯确系**路由缺席**：`mcp add` 经 `_dispatch` 落进
      **REPL** 并阻塞（`--command` 的 argparse dest 与顶层 `dest="command"` 冲突，把
      `args.command` 覆盖成 `None`）；改 dest 后红转绿

## 2. 实现（绿）
- [x] 2.1 `src/core/mcp/endpoints.py`：`mcp_endpoints_path` / `EndpointRecord` / `manifest()` /
      `default_endpoint_name` / `MCPEndpointRegistry`（原子写 + 降级告警）
- [x] 2.2 `src/core/mcp/client.py`：`connect(..., handle_id=)`；`add` 用安装名作 `handle_id`；重装先释放
- [x] 2.3 `src/core/mcp/errors.py`：`ENDPOINT_NAME_CONFLICT`
- [x] 2.4 `src/core/mcp/__init__.py`：导出新符号
- [x] 2.5 `src/core/runtime.py`：装配期读注册表 → 安装管线 → 失败降级告警
- [x] 2.6 `src/core/entry.py`：`_mcp_add` / `_mcp_list` / `_mcp_remove` + `add --name`
- [x] 2.7 绿证：全量 pytest 通过，无回归

## 3. 规格
- [x] 3.1 `mcp` spec delta：MODIFIED「MCP Server 安装与移除」
- [x] 3.2 新增场景：端点跨进程持久化 / 装配期注册远端工具 / 不可达端点降级不阻断装配 /
      端点名冲突拒绝 / mcp list 列出已安装端点
- [x] 3.3 `openspec validate 0074-mcp-endpoint-registry` 通过

## 4. 文档
- [x] 4.1 `doc/03-interfaces/mcp-interface.md`：§6 命令形状 + 注册表 + 降级口径；错误码表补 `ENDPOINT_NAME_CONFLICT`
- [x] 4.2 `doc/02-modules/mcp.md`：§3.x 注册表与装配期注册；工具命名 `mcp.<端点名>.<工具>`
- [x] 4.3 `doc/04-testing/test-cases.md`：TC-MCP-10
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0071 + 变更追踪行
- [x] 4.5 `doc/02-modules/cli-ops.md` / `coding-plan/phase-12.md` 两条 `[ ]` 改记 change id

## 5. 收口
- [x] 5.1 手动归档（合并 delta + 移动目录）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 `coding-plan/phase-19.md`：B4 行标关闭 + §4 B4 段替换；`coding-plan/README.md` 更新
- [x] 5.4 四门复跑 + 记忆更新 + 提交
