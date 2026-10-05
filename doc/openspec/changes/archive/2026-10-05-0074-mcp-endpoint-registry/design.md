# design — MCP 端点注册表与 CLI 接线（change 0074）

## 决策 1：落 `$CORE_STATE_DIR/mcp-endpoints.json`（而非配置段）

`mcp add` 的语义是**运行期安装**（规格原文），端点因此是**状态**不是**配置**：它由命令行写入、
带连接句柄语义，且不应参与 `config show/set` 的校验面（`ConfigSpec` 是「用户可声明的键」的
单一真源，端点名是**开放集合**——同 `features.<模块>` 之于 `GATABLE_MODULES`，ADR-0065）。
故沿用 `pets.json` / `evolution-pending.json` / `checkpoints.jsonl` 的状态文件约定。

**取 JSON 单文件 + 原子写**（tmp → `os.replace`）：与 `skills.persist` / `pet.core.manager`
同形；`0062` 已证明「先截断再整写」会整体丢失。

## 决策 2：装配期**连接并注册**，失败降级

选「装配期连接注册」（用户裁决，见账本 B4）：
`build_runtime` 反序列化记录 → 构造 `InstallableAsset(kind=MCP, source=MCP_ENDPOINT, manifest=…)`
→ `InstallDispatcher.install(asset)`。**复用既有安装管线**（discover→install 的执行半边），
不新造适配路径 ⇒ 远端工具走的是与 `0054` 完全相同的
`MCPClient.add → MCPToolAdapter.adapt → ToolProvider.register`。

代价与取舍：`build_runtime` 被多数命令调用（`config show` / `evolve` / `pet` / `ui serve` …），
故**配了端点就意味着这些命令都会拉起子进程/建连接**。接受，理由：
① 与规格「进入现有连接管理」一致（装配即纳入管理）；
② 惰性（首次调用才连接）要多一层代理 Tool 与一套「调用期连接失败」语义，YAGNI；
③ 失败**只告警不阻断**（`warnings.warn`），故不会出现「端点坏 ⇒ 所有命令不可用」。

## 决策 3：工具命名跨进程稳定 —— 命名安装以**安装名**为 `handle_id`

`connect()` 原是 `uuid4().hex` 作 `handle_id` ⇒ `tool_id = mcp.<uuid>.<工具>` 每次都变。
持久化之后这不可接受（重启后同名工具消失，白名单/授权/记忆引用全部失配）。
改法：`connect(endpoint, *, handle_id=None)`，`add()` 传**安装名** ⇒ `mcp.<端点名>.<工具>`，
与 `doc/02-modules/mcp.md:47`「包装为 `mcp.<server>.<tool>` 命名空间」对齐。
匿名 `connect()`（无 name）保持 uuid 兜底，行为不变。

## 决策 4：名称派生与冲突

- `--name` 显式优先；缺省 URL → `urlparse(...).hostname`；命令行 → `shlex.split()[0]` 的基名。
- **重名拒绝**（`ENDPOINT_NAME_CONFLICT`，退出码 1）：派生名可能撞车（两条 `npx …` 都派生
  `npx`），静默覆盖会**丢掉另一个端点的配置** —— 与 B5/E20 的「不静默」一脉。
  修正路径明确：`--name` 换名，或先 `mcp remove`。

## 决策 5：先连通验证再落盘

`mcp add` 顺序 = 解析 → 连接（`MCPClient.add` 内含 initialize 握手 + 版本校验）→ 适配注册 →
**成功后才写注册表**。失败不落盘：避免把「打不通的端点」持久化进配置，让后续每次装配都
徒劳重试并告警。

## 决策 6：`mcp remove` 的对称性

一次性进程里 `PluginInstaller._assets` 是空的，故 `remove` 由**注册表记录**反建 asset：
`installer.register(asset, StubPlugin(name, manifest))` → `installer.uninstall(name)`
（走 deactivate → unload → uninstaller → `dispatcher.uninstall` 反注册 + 释放连接），
**最后**才从注册表删除。顺序保证「释放失败不应留下已删除的配置」。

## 已知取舍 / 未做

- `mcp list` **不连接**、不列工具：列表是配置面事实；工具面在装配后由 agent 的工具集呈现
  （`core-agent tools` / `tools/list`）。避免为「看一眼」拉起全部子进程。
- 装配期连接的**超时**沿用传输层既有超时；端点宕机时 `mcp add` 的等待即该超时。
- 无并发写保护（注册表只在 CLI 一次性进程里写；不做跨进程锁 —— 与 `pets.json` 同层）。
