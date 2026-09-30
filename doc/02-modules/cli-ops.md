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
- **连接**：mcp add / mcp remove / mcp list，复用 mcp 安装/移除生命周期。
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
