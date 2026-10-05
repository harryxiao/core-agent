# MCP 端点注册表与 CLI 接线（mcp-endpoint-registry）

## Why

账本 **B4**（`mcp` CLI 接线 + 端点注册表持久化）。规格「MCP Server 安装与移除」以
**CLI 面**写场景（「**WHEN** 执行 mcp add」/「**WHEN** 执行 mcp remove」），
`cli-ops` 规格亦要求 `mcp add / mcp remove / mcp list`「复用插件来源与安装生命周期」；
而一手核实：`entry._mcp` 对非 `serve` 子命令落兜底「已识别，尚未接线」⇒ **规格场景在生产不可达**。

安装管线本身**已齐备**（change `0054`）：`InstallDispatcher._install_mcp` 走
`MCPClient.add` → `MCPToolAdapter` → `ToolProvider.register`，卸载走
`_uninstall_mcp`（反注册工具 + `MCPClient.remove` 释放连接/子进程）。缺的是三件：

1. **CLI → 安装管线的接线**（`add` / `list` / `remove` 三个 handler）；
2. **端点跨进程持久化** —— CLI 每次都是**一次性进程**（`_build_installer()` 每次新建、
   `MCPClient` 随即销毁），不落盘则 `mcp add` 连上即丢，与 `plugin install` 一样是
   「**看起来成功、实则空转**」；且 `build_runtime` 无处得知用户装过什么 ⇒ 远端工具
   **永远不会**进入 agent 的工具集（规格「其工具可被动态发现」在生产不成立）；
3. **稳定工具命名** —— `MCPClient.connect` 用 `uuid4().hex` 作 `handle_id`，
   `tool_id` 形如 `mcp.<uuid>.<工具>`，**每次连接都变**；`doc/02-modules/mcp.md` 写的是
   `mcp.<server>.<tool>`。工具名跨进程漂移则按名授权/白名单/记忆引用**无从谈起**
   （`mcp add` 之后再重启，昨天允许的工具名今天不复存在）。

## What Changes

- `src/core/mcp/endpoints.py`（新）
  - `mcp_endpoints_path()`：`$CORE_STATE_DIR`（缺省 `~/.core/state`）/`mcp-endpoints.json`
    —— 与 `checkpoints.jsonl` / `pets.json` / `evolution-pending.json` 同状态目录约定。
  - `EndpointRecord`（`name` / `source` / `transport` / `command` / `args`）+
    `manifest()`：转成 `InstallDispatcher._install_mcp` 消费的 manifest 形状（**单一解析点**）。
  - `default_endpoint_name(source, command)`：URL → 主机名；命令行 → 命令基名。
  - `MCPEndpointRegistry(path)`：`list` / `get` / `add` / `remove`，**原子写**（tmp + `os.replace`，
    同 change `0062`）；文件损坏或条目残缺 → `warnings.warn` **降级跳过**（同 E18 告警口径），
    不静默丢配置也不阻断启动。
- `src/core/mcp/client.py`：`connect(endpoint, *, handle_id=None)`；`add` 以**安装名**作
  `handle_id`（`mcp.<端点名>.<工具>`，跨进程稳定，与模块文档对齐）；同名重装先释放旧连接。
- `src/core/runtime.py`：装配期读注册表 → 逐端点 `dispatcher.install(asset)`（**复用既有安装管线**）
  → 远端工具进 `ToolProvider`；**单个端点不可达只告警不阻断装配**（同 `MCPEndpointRegistry` 口径）。
- `src/core/entry.py`：
  - `mcp add <endpoint> [--name N] [--transport T] [--command C] [--args ...]`：**先连通验证再落盘**
    （连不上不落盘，退出码 1）；打印端点名与发现的工具；重名拒绝（不静默覆盖）。
  - `mcp list`：读注册表列出已安装端点（name / transport / 目标），不连接。
  - `mcp remove <name>`：注册表删除 + 本进程若已连接则释放（`MCPClient.remove`）。
- `src/core/mcp/errors.py`：新增错误码 `ENDPOINT_NAME_CONFLICT`。
- 规格 delta：`mcp` spec **MODIFIED**「MCP Server 安装与移除」（CLI 命令形状 / 持久化 /
  装配期注册 / 降级口径 / 稳定工具命名）。

## What Does NOT Change

- **不**引入原生列表配置（仍无 `mcp` 配置段）；端点注册表是**运行期状态**，不是配置项
  —— 与 `pets.json` / `evolution-pending.json` 同层。
- **不**改 `PluginInstaller` / `SourceResolver` 契约（`mcp add` 自行解析端点形状，见 design）。
- **不**做 `mcp add` 的暖连接复用、不做热重载（进程内一次装配一次连接）。
- **不**动 `plugin install --kind mcp`（其 resolver 仍只认本地 manifest，属独立变更）。
