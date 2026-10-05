# mcp spec delta — mcp-endpoint-registry（change 0074 / 账本 B4）

**把「MCP Server 安装与移除」的 CLI 面接上，并让安装成果活过一次性进程。**

规格以 CLI 面写场景（「**WHEN** 执行 mcp add」），而 `entry._mcp` 对非 `serve` 子命令落兜底
「已识别，尚未接线」⇒ 场景在生产不可达。安装管线（`MCPClient.add` → 适配 → `ToolProvider.register`
/ `remove` → 反注册 + 释放）本身齐备（change `0054`），缺的是接线、持久化与稳定命名。

## MODIFIED Requirements

### Requirement: MCP Server 安装与移除
系统 SHALL 支持在运行时安装与移除 MCP 服务端，来源覆盖本地 stdio（command+args 拉起本地进程）与远端 http/streamable-http（url+headers）两类：安装复用插件来源（mcp-endpoint）经 discover → verify → install → register 进入现有连接管理；移除经 deactivate → uninstall 释放连接资源（含本地子进程销毁）。

安装与移除 SHALL 经 CLI 面暴露，命令形状为 `mcp add <endpoint> [--name N] [--transport T] [--command C] [--args ...]` / `mcp remove <name>` / `mcp list`。**端点 SHALL 跨进程持久化**（`$CORE_STATE_DIR/mcp-endpoints.json`，原子写），且 `mcp add` SHALL **先完成连接握手**再落盘 —— 连不上的端点 SHALL NOT 被持久化。端点名 SHALL 由 `--name` 显式指定，缺省按来源派生（URL → 主机名，命令行 → 命令基名）；**同名端点 SHALL 被拒绝**（`ENDPOINT_NAME_CONFLICT`），SHALL NOT 静默覆盖既有端点配置。组合根 SHALL 在装配期读取注册表并复用安装管线连接各端点、把远端工具注册进本地工具集合，工具名 SHALL 形如 `mcp.<端点名>.<工具>`（**跨进程稳定**，不得因重连而漂移）；**单个端点连接失败 SHALL 降级为告警并跳过，SHALL NOT 阻断装配**，注册表文件损坏或条目残缺 SHALL 同样降级告警（不静默丢弃、不阻断启动）。`mcp remove` SHALL 先释放连接（含本地子进程销毁）再从注册表摘除。

#### Scenario: 运行时安装 MCP Server
- **GIVEN** 一个 MCP 服务端来源（mcp-endpoint）
- **WHEN** 执行 mcp add
- **THEN** 安装并注册该 MCP 服务端，进入现有连接管理，其工具可被动态发现

#### Scenario: 安装本地 stdio MCP Server
- **GIVEN** 一个本地 MCP 服务端来源（stdio，command+args）
- **WHEN** 执行 mcp add
- **THEN** 以沙箱受控子进程拉起并注册，进入连接管理，其工具可被动态发现

#### Scenario: 安装远端 http MCP Server
- **GIVEN** 一个远端 MCP 服务端来源（http/streamable-http，url+headers）
- **WHEN** 执行 mcp add
- **THEN** 建立网络连接并注册（经出站白名单管控），进入连接管理，其工具可被动态发现

#### Scenario: 移除 MCP Server
- **GIVEN** 一个已安装的 MCP 服务端
- **WHEN** 执行 mcp remove
- **THEN** 停用并卸载该服务端，释放连接/会话/socket 资源（含本地子进程销毁），相关工具标记不可用

#### Scenario: 按来源形状构建端点
- **GIVEN** 一个 MCP 服务端来源字符串（`http(s)://` URL 或本地命令行）
- **WHEN** `MCPClient.add` 安装该来源
- **THEN** URL 构建 http 端点（url+headers），命令行构建 stdio 端点（command+args）；显式 transport/command 覆盖形状推断

#### Scenario: 端点跨进程持久化
- **GIVEN** `mcp add` 成功安装了一个端点
- **WHEN** 该 CLI 进程退出、另起一个进程执行 `mcp list`
- **THEN** 该端点仍在列（已落 `$CORE_STATE_DIR/mcp-endpoints.json`）—— 安装成果不随一次性进程消失

#### Scenario: 连接失败不落盘
- **GIVEN** 一个不可达的 MCP 服务端来源（命令不存在 / 连接被拒）
- **WHEN** 执行 `mcp add` 且握手失败
- **THEN** 命令以非零退出码失败且**不落盘** —— 不把打不通的端点持久化（避免此后每次装配徒劳重试）

#### Scenario: 端点名冲突拒绝
- **GIVEN** 已存在名为 `X` 的端点
- **WHEN** 以同名（缺省派生或 `--name X`）执行 `mcp add`
- **THEN** 以 `ENDPOINT_NAME_CONFLICT` 拒绝且**不覆盖**既有端点配置（换名或先 remove 才可再装）

#### Scenario: 装配期注册远端工具（稳定命名）
- **GIVEN** 注册表含一个可达端点（名为 `files`）
- **WHEN** 组合根装配运行时
- **THEN** 连接该端点并把其工具注册进本地工具集合，工具名形如 `mcp.files.<工具>`；再次装配（新进程）命名**逐字相同**

#### Scenario: 不可达端点降级不阻断装配
- **GIVEN** 注册表含一个不可达端点与一个可达端点
- **WHEN** 组合根装配运行时
- **THEN** 装配**照常完成**（告警而非异常），可达端点的工具仍被注册 —— 坏端点不得让整个系统不可用

#### Scenario: 注册表损坏降级告警
- **GIVEN** `mcp-endpoints.json` 内容损坏（非法 JSON）或含残缺条目（缺 name/source）
- **WHEN** 读取注册表（装配期或 `mcp list`）
- **THEN** 告警并跳过该文件/条目（其余条目照常生效），SHALL NOT 静默丢弃、SHALL NOT 阻断启动

#### Scenario: mcp list 列出已安装端点
- **GIVEN** 注册表含若干已安装端点
- **WHEN** 执行 `mcp list`
- **THEN** 列出各端点的名字与来源/传输，且**不建立连接**（列表是配置面事实）
