# 模块设计：CLI 运维命令面（CLI Ops）

> 对应规格：`doc/openspec/specs/cli-ops/spec.md` ｜ 接口：`doc/03-interfaces/cli-ops-interface.md`
> 定位：**横切 ｜ 运维命令集与启动参数映射**，统一命令入口承载六组命令，ConfigSpec 驱动 CLI flag / env / config.yaml 三层参数一一对应。

---

## 1. 模块定位

CLI 运维命令面（cli-ops）为 core-agent 提供**运维命令集与启动参数映射**：以统一命令入口承载生命周期、状态、资产、连接、安全、网关六组命令，并以 ConfigSpec 单一真源驱动 CLI flag / env / config.yaml 三层参数一一对应。

命令面只管「怎么发命令、参数怎么映射」，实际的进程守护、插件安装、MCP 生命周期复用既有模块，不重复实现。

---

## 2. 内部组成

```
CLI Ops（横切）
├── CLICommandDispatcher 命令分发：lifecycle / status / asset / connection / security / gateway
├── CommandGroup        六组枚举：LIFECYCLE / STATUS / ASSET / CONNECTION / SECURITY / GATEWAY
└── ParamMapper         启动参数映射：resolve / generate_cli / generate_env / generate_yaml_schema
```

> 配置项单一真源 `ConfigSpec`（key / cli_flag / env_var / default / map_to / exposure）的权威定义见 `configuration-interface.md`，ParamMapper 消费它、不重复定义。

---

## 3. 关键设计

### 3.1 六组运维命令

- **生命周期**：start / stop / restart / kill 进程守护。
- **状态**：status / doctor / logs / version / help 状态查询，不改变运行态。
- **资产**：install / uninstall / list / info，复用 plugin-registry 插件来源与安装生命周期。
- **连接**：mcp add / mcp remove / mcp list，复用 mcp 安装/移除生命周期（change `0074` 已接线）。
- **安全**：auth / permission-mode。
- **网关**：gateway 启停本地服务网关。

### 3.2 启动参数映射与单一真源

- 启动参数与配置项一一对应：`--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR`，映射关系由 ConfigSpec 声明。
- 优先级链固定为 **CLI flag > env > config.yaml > 默认值**，同项多处定义时高优先级覆盖低优先级。
- CLI 参数面 / env 变量面 / yaml schema 均由 ParamMapper 从 ConfigSpec 生成，含 core/advanced/hidden 分级，无第二真源。

### 3.3 复用既有生命周期

- 资产命令复用 plugin-registry 的插件来源与安装生命周期；连接命令复用 mcp 的安装/移除生命周期，命令面只做路由与参数透传。
- 状态查询类命令不改变运行态，与生命周期类命令职责分离。

---

## 4. 命令面闭环

```
argv ──dispatch──► 六组命令之一 ──► 进程退出码
启动参数 ──resolve──► 优先级链取值（CLI flag > env > config.yaml > 默认值）
ConfigSpec ──generate_*──► CLI 参数面 / env 变量面 / yaml schema（一一对应）
```

- 命令路由与参数映射都由 ConfigSpec 单一真源收敛，配置项定义一处、三面生成，杜绝参数面漂移。
- 非法 map_to（目标不存在或冲突）在启动时阻断，防止映射错配进入运行期。

**会话命令族（change 0116 / ADR-0109）**：`session create`（新建并登记共享注册表）、
`session list`（枚举标识 + 模式）、`session show <session_id>`（打印该会话转录，取自内核回灌的
**同一** `TranscriptStore`；无转录 ⇒ 明示、退出码 0；未登记 ⇒ 非零退出码）；无子命令的交互入口接受
顶层 `--session <session_id>` **续聊**既有会话（复用标识、不新建；未登记 fail-closed）。语义与
`run --session` 一致（同 `dest`；`argparse` 子解析器默认值不覆盖已置属性 ⇒ 二者不冲突）。

**一次性任务入口的会话归因（change `0190`／ADR-0180）**：`task <目标>` 新任务铸会话时经**同一**
跨进程共享注册表登记（mode `cli`，**不**另建第二注册表）—— 铸出的会话对 `session list` 可见、对
交互入口 `--session` 续接可用；任务续跑（`--resume`）**复用**检查点携带的既有会话（不另铸新会话，
同一任务轨迹不分裂），检查点为旧占位值 / 未携带会话时视作未归属并提示（不迁移旧数据）。

**入口启动呈现未完成任务（change `0191`／ADR-0181；**全入口覆盖** change `0207`／ADR-0197）**：一次性
任务入口（`task <目标>`，新任务）与常驻服务入口（`serve`）**启动时**扫描检查点并**呈现**未完成任务 ——
告警 + 打印「N 个未完成任务：`task --resume <id>` 可续跑」（只报 task id，不回显任务正文）；**只呈现不
重执行**（`recover()` 无 replay 回调 = 纯扫描，守 P2 副作用不自动重放）。**change `0207` 补全覆盖**：
`REPL` / `run` / `app` 三入口经 `_build_ui(..., surface_recovery=True)` **一旗即成**（`0191` 已为 `serve`
建好机制），`mcp serve` 自建 runtime（无 `UIAPILayer`）故在 `build_runtime` 后**显式**补调一次
`_surface_incomplete` —— 五入口（`REPL`/`run`/`serve`/`app`/`mcp serve`）启动路径**全部**呈现。呈现走
**stderr**（`mcp serve` 的 stdout 是协议流，SHALL NOT 污染）。任务续跑（`--resume`）取**时间戳最新**检查点
重建续跑状态（与崩溃恢复 `restore` 的 ts 序同口径）。

---

## 5. 错误处理

| 错误码 | 行为 |
|---|---|
| `UNKNOWN_COMMAND` | 未识别的 CLI 命令 |
| `INVALID_MAP_TO` | ConfigSpec 中 map_to 非法（目标不存在或冲突），阻断启动 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/cli-ops-interface.md`
- 规格：`doc/openspec/specs/cli-ops/spec.md`
- 单一真源：`doc/03-interfaces/configuration-interface.md`（ConfigSpec 权威定义）
- 复用：`doc/02-modules/plugin-registry.md`（资产命令）、`doc/02-modules/mcp.md`（连接命令）
- 架构：`doc/01-architecture/architecture-overview.md`（横切 cli-ops）
