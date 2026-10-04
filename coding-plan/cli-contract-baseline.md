# core-agent CLI 契约基线（cli-contract-baseline）

> 本文件是「coding-plan 最后一环」的 CLI 契约基线交付物，供 claude code 在开始编码前对齐命令面、参数面、配置面的统一契约。
> 生成方式：走查 specs(25)/changes(27)/interfaces(23)/modules(18) + 源码实测（configuration 模块），经去重、按 L0-L5 分层、正向推演后敲定。
>
> ⚠️ **本文件是 Phase 早期的「设计态快照」，非规范文件**：与实现冲突时**以 `doc/openspec/specs/` 为准**
> （例：§10 的内置工具清单长期与实现/规格不一致，已于 change `0056` 订正）。
>
> **溯源锚点（源码实测，非推演）**：
> - `_ENV_OVERRIDES` 7 键：`src/core/configuration/manager.py` L24-33
> - `_FEATURE_ENV_PREFIX = "CORE_FEATURES_"`：manager.py L35
> - env 覆盖机制：`_apply_env` env **无条件覆盖** yaml 同键（L149-157）
> - schema 校验：manager.py L70-91；dataclass：`src/core/configuration/models.py`
> - 架构锚点：`coding-plan/architecture-audit.md` L0-L5 覆盖矩阵 + 微调计划 M1-M6

---

## 0. 边界铁律（先读，决定哪些「算 CLI」）

1. **UIAPILayer 9 方法 = 三桥统一命令面核心锚点**（关键结论 6/7）：
   - create_session / run_loop 经 CLI 子命令（`session create` / `run`）暴露；其余 7 方法（barge_in / get_memory / compact / list_tools / invoke_tool / get_llm_config / set_llm_config）经三桥统一 API（SSE/WS）暴露。
   - 内置工具 `tools.*`、SafetyGate 交互（confirm/ask）、SSE 事件、五阶段 loop 协议——全部走运行时协议（SSE/WS/API），**不进 CLI 命令面**。
2. **SSE 事件是前端流式协议**，属 CLI 基线「必选联动项」而非命令。
3. **CLI 覆盖四类**：① 启动/生命周期/运维入口；② 配置读写校验；③ 资产管理（MCP/插件/技能）与分发；④ 会话/运行（`session create` / `run`，UIAPILayer 核心锚点）。运行时其余能力走统一 UIAPILayer。

---

## 1. 命令面总览（32 动词 + 14 全局 flag）

| 子命令族 | 命令动词 | 层 | 缺口归属 |
|---|---|---|---|
| 顶层入口 | core-agent / serve / app | L0 | 三模桥接 |
| 生命周期/运维 | start/stop/restart/probe/status/doctor/sessions | L0 | probe 已有；status/doctor 补缺口B |
| 配置 | config show/validate/get/set | 横切 configuration | ConfigManager |
| MCP | mcp serve/list/add/remove | 横切 mcp | add/remove 补 M2 |
| 插件/资产安装 | plugin install/uninstall/list | L0 扩展 PluginSource | 补 M1/M3 |
| 技能市场 | skill search/install/remove | L3 skillhub | install=plugin --kind skill 别名 |
| 会话/运行 | session create + run | L1 UIAPILayer | 命令面核心锚点 |
| 记忆维护 | memory maintain | L2 memory | 补（change `0049`：一次性压实 + 遗忘） |
| 进化冷路径 | evolve run | L4 evolution | 补（change `0051`：一次性强制跑一轮冷路径） |
| 分发 | release publish/upgrade/rollback | L5 ReleaseManager | 补 |
| 宠物 | pet <verb> | 编排层扩展 pet-mode | 补 M6（三入口之一，子动词面见 pet-mode-interface §3） |
| 神兽 | summon <beast> [task] / recall <beast> | 编排层扩展 beast-mode | 补 M7（前台重大任务，三入口见 beast-mode spec） |

---

## 2. CMD 清单表

### 2.1 顶层入口（3）

| # | 命令 | 语义 | 实现佐证 |
|---|---|---|---|
| 1 | `core-agent` | CLI/TUI 模式，Textual 直连内核（同进程无 IPC），**不绕过统一 UIAPILayer** | 文档层契约，src/ 无入口[需确认] |
| 2 | `core-agent serve [--host H] [--port P]` | Web 模式，HTTP + SSE 打开单 SPA | 印证 `WebBridge.serve(host,port)` |
| 3 | `core-agent.app` | Desktop 模式，Tauri 壳 + sidecar 拉起 Python 后端 | 印证 `DesktopBridge.start_sidecar()` |

### 2.2 生命周期/运维（L0 · 7）

| # | 命令 | 语义 | 对应类/方法 | 缺口 |
|---|---|---|---|---|
| 4 | `core-agent start [--profile P]` | 启动实例 | LifecycleController | 已有 |
| 5 | `core-agent stop` | 停止实例 | LifecycleController | 已有 |
| 6 | `core-agent restart` | 重启实例 | LifecycleController | 已有 |
| 7 | `core-agent probe [--format json]` | 健康探针 → HealthStatus{alive,detail}，exit 0=alive/1=down | LifecycleController.probe() | 印证 |
| 8 | `core-agent status` | 运行状态概览（进程/会话/队列） | — | **补缺口B（运维命令集）** |
| 9 | `core-agent doctor` | 自检诊断（配置/密钥/网络/依赖/权限） | — | **补缺口B（运维命令集）** |
| 10 | `core-agent sessions` | 枚举托管会话 | HarnessHost.sessions | 印证 |

### 2.3 配置（横切 configuration · 4）

| # | 命令 | 语义 | 对应方法 | 说明 |
|---|---|---|---|---|
| 11 | `core-agent config show [--format yaml\|json] [--effective]` | 显示有效配置（env>yaml>default 合并） | ConfigManager.load() | 只读 |
| 12 | `core-agent config validate [--file PATH]` | 校验 config.yaml → ValidationResult{ok,errors} | validate_schema() | 只读 |
| 13 | `core-agent config get <key>` | 读单键（feature 用 is_enabled） | get/is_enabled | 只读 |
| 14 | `core-agent config set <key> <value>` | 运行时变更，变更即生效/失败回滚 | apply_change() | 写 |

### 2.4 MCP（横切 mcp · 4，补 M2）

| # | 命令 | 语义 | 对应 | 缺口 |
|---|---|---|---|---|
| 15 | `core-agent mcp serve --transport {stdio\|http\|streamable-http} [--endpoint E]` | 启动 MCP server（client/server 双向） | MCPServer.serve | 已有；streamable-http[需确认] |
| 16 | `core-agent mcp list` | 列出已注册 MCP 端点/工具 | MCPEndpoint | **补 M2** |
| 17 | `core-agent mcp add <endpoint> [--transport T] [--command C] [--args ...]` | 运行期添加 MCP 端点 | MCPEndpoint 字段 | **补 M2** |
| 18 | `core-agent mcp remove <name>` | 移除 MCP 端点 | — | **补 M2** |

### 2.5 插件/资产安装（L0 扩展 PluginSource · 3，补 M1/M3）

| # | 命令 | 语义 | 缺口 |
|---|---|---|---|
| 19 | `core-agent plugin install <asset> [--kind skill\|mcp\|cli]` | 安装三方资产（InstallableAsset{kind}） | **补 M1（统一资产入口）** |
| 20 | `core-agent plugin uninstall <name>` | 卸载资产 | **补 M1** |
| 21 | `core-agent plugin list [--kind ...]` | 枚举已装资产 | **补 M1** |

### 2.6 技能市场（L3 skillhub · 3）

| # | 命令 | 语义 | 说明 |
|---|---|---|---|
| 22 | `core-agent skill search <query>` | 搜索技能市场 | SkillHubClient.search |
| 23 | `core-agent skill install <name> [--source official\|...]` | 安装技能 | = `plugin install --kind skill` 别名 |
| 24 | `core-agent skill remove <name>` | 卸载技能 | = `plugin uninstall` 别名 |

### 2.7 会话/运行（L1 UIAPILayer · 2，核心锚点）

| # | 命令 | 语义 | 对应方法 |
|---|---|---|---|
| 25 | `core-agent session create [--profile P]` | 新建会话 | UIAPILayer.create_session() |
| 26 | `core-agent run [--prompt "..." \| --file task.md] [--session ID] [--max-turns N]` | 运行一轮/一个任务 | UIAPILayer.run_loop() + AgentLoop.max_turns |
| 26b | `core-agent memory maintain` | 触发一次记忆维护（压实 + 遗忘归档），打印归档条数 | MemoryStore.compact() + forget() |
| 26c | `core-agent evolve run` | 装配 runtime → **强制**跑一轮进化冷路径（诊断/提案），打印结局（`status` 或 `no_op`）；一次性动作、不改运行态 | EvolutionWorker.maybe_run(force=True) |

### 2.8 分发（L5 ReleaseManager · 3）

| # | 命令 | 语义 | 对应方法 |
|---|---|---|---|
| 27 | `core-agent release publish <bundle>` | 发布 bundle | ReleaseManager.publish() |
| 28 | `core-agent release upgrade <version>` | 升级 | ReleaseManager.upgrade() |
| 29 | `core-agent release rollback` | 回滚 | ReleaseManager.rollback() |

### 2.9 宠物（pet-mode · 补 M6）

| # | 命令 | 语义 | 对应 | 缺口 |
|---|---|---|---|---|
| 30 | `core-agent pet <verb> [...]` | 激活/枚举/停止宠物（后台自治会话），三入口之一 | `PetActivator.activate_from_cli(verb, rest)` / `PetManager` | **补 M6（子动词面待 phase-9 敲定，见 pet-mode-interface §3）** |

### 2.10 神兽（beast-mode · 补 M7）

| # | 命令 | 语义 | 对应 | 缺口 |
|---|---|---|---|---|
| 31 | `core-agent summon <beast> [task]` | 召唤神兽执行前台重大任务（异步并发，完成后自动回归），三入口之一 | `BeastActivator.activate_from_cli(beast, rest)` / `BeastManager.summon` | **补 M7（异步执行经 handoff→loop.arun）** |
| 32 | `core-agent recall <beast>` | 手动复位目标神兽至 RECALLED（可再次召唤），他兽不受影响 | `BeastActivator.recall_from_cli(beast)` / `BeastManager.recall` | **补 M7** |

> `beast list` 枚举 20 只内置神兽（只读，`BeastRegistry.all()`），属 read 查询，非独立动词。

### 2.11 全局 flag（启动参数，非子命令 · 14）

| # | flag | 语义 | 落点 |
|---|---|---|---|
| F1 | `--profile P` | Bundle 组合清单 | CompositionEngine.resolve(profile) 入参，独立文件（非 config.yaml） |
| F2 | `--cwd DIR` | 工作目录 | 项目 cwd（全局 profile `~/.core/Core.md` 为文件约定） |
| F3 | `--config PATH` | config.yaml 路径 | 默认 `Path("config.yaml")` 相对 cwd |
| F4 | `--permission-mode {read-only\|interactive\|auto-approve\|high-risk-block}` | 权限模式 | M6 横切 permission（枚举成员[需确认]） |
| F5 | `--feature-<name>[=bool]` | feature flag 覆盖 | `features.*` 同源，is_enabled 读取 |
| F6-F9 | `--llm-provider/--llm-model/--llm-endpoint/--llm-api-key` | LLM 配置覆盖 | M5 ConfigSpec，CLI flag 覆盖层 |
| F10-F12 | `--im-gateway/--im-corp-id/--im-secret` | IM 配置覆盖 | M5，CLI flag 覆盖层 |
| F13 | `--verbose/--quiet/--log-level LEVEL` | 日志 | observability 段 |
| F14 | `--version/--help` | 版本/帮助 | 通用 |

---

## 3. 参数优先级链

```
CLI flag  >  env var  >  config.yaml  >  默认值
```

- ✅ 已实测：`env var > config.yaml`（`_apply_env` 覆盖 yaml 同键）
- ⚠️ 待确认：CLI flag 层是否已实现（三模入口未实现 → CLI 层大概率仅设计态）

---

## 4. 参数清单表

### 4.1 已锚定（源码实测 7 项）

| # | CLI flag（推演） | env var | 默认 | yaml 段.键 | dataclass 字段 | schema 校验 | 状态 |
|---|---|---|---|---|---|---|---|
| 1 | `--llm-provider` | `CORE_LLM_PROVIDER` | 无(必选) | `llm.provider` | `LLMConfig.provider` | 非空必选 | ✅已锚定 |
| 2 | `--llm-model` | `CORE_LLM_MODEL` | 无(必选) | `llm.model` | `LLMConfig.model` | 非空必选 | ✅已锚定 |
| 3 | `--llm-endpoint` | `CORE_LLM_ENDPOINT` | 无(必选) | `llm.endpoint` | `LLMConfig.endpoint` | 非空必选 | ✅已锚定 |
| 4 | `--llm-api-key` | `CORE_LLM_API_KEY` | 无(必选) | `llm.api_key` | `LLMConfig.api_key_ref` ⚠️ | `${VAR}` 引用 + 非空 + 可解析 | ✅已锚定 |
| 5 | `--im-gateway` | `CORE_IM_GATEWAY` | `""` | `im.gateway` | `IMConfig.gateway` | ❌无校验 | ✅已锚定 |
| 6 | `--im-corp-id` | `CORE_IM_CORP_ID` | `""` | `im.corp_id` | `IMConfig.corp_id` | ❌无校验 | ✅已锚定 |
| 7 | `--im-secret` | `CORE_IM_SECRET` | `""` | `im.secret` | `IMConfig.secret_ref` ⚠️ | 仅明文拒绝(不强制非空/可解析) | ✅已锚定 |

### 4.2 外推：features 前缀机制（`CORE_FEATURES_` 外推）

| CLI flag（推演） | env var | 默认 | yaml 键 | 说明 |
|---|---|---|---|---|
| `--feature <name>` / `--feature <name>=on\|off` | `CORE_FEATURES_<NAME>` | `false` | `features[<name>.lower()]` | 值 ∈ `{"true","1","yes"}` 才为 True；**无固定模块清单，任意 name 可注册** |

### 4.3 外推：extra 兜底段（透传）

| yaml 形态 | 映射目标 | 校验 | 说明 |
|---|---|---|---|
| 任意非 `llm/features/im` 段 | `AppConfig.extra`（dict[str,Any]） | ❌无校验 | 透传，供三方插件/技能自定义键；与 `config set` 写回对应 |

### 4.4 MCP / 插件 / 技能 运行参数（待实现态）

| CLI flag（推演） | 映射目标 | 状态 |
|---|---|---|
| `--transport stdio\|http\|streamable-http`（serve 子命令） | MCP transport 选择 | 命令面已确认，实现待验 |
| `--endpoint <url>` / `--name <name>`（mcp add/remove） | MCP 端点注册 | 待确认 |
| `--source <url/path>`（plugin/skill install） | 插件/技能来源 | 待确认 |

---

## 5. 键名不一致陷阱（⚠️ 核心，必须敲定）

| 概念层 | yaml 键（env 同） | dataclass 字段 | CLI flag（推演建议） |
|---|---|---|---|
| LLM API Key | `api_key` | `api_key_ref` | `--llm-api-key` |
| IM Secret | `secret` | `secret_ref` | `--im-secret` |

**敲定规则**：
1. CLI flag 用业务名（`api-key`/`secret`），不暴露 `_ref` 后缀。
2. 写回 config.yaml 用 yaml 键（`api_key`/`secret`）。
3. dataclass 字段保持 `_ref` 后缀（表示"引用而非明文"语义）。
4. 实现时须维护 env/yaml/dataclass/flag 四方对照，避免同名坑。

---

## 6. secret 解析规则（api_key / secret 专项）

| 项 | api_key_ref（llm） | secret_ref（im） |
|---|---|---|
| yaml 明文 | ❌ 拒绝 | ❌ 拒绝（仅 im 存在时） |
| 合法形态 | `${VAR}` 或 `secret:{name}` | 同左 |
| 解析链路 | `resolve_secret` → env → keychain | 同左 |
| 非空强制 | ✅ 强制非空 | ❌ 不强制 |
| 可解析强制 | ✅ 必须可解析 | ❌ 不强制 |

> ⚠️ **不对称性**：`api_key_ref` 三重强制（非空+引用+可解析），`secret_ref` 仅明文拒绝。`im.gateway`/`im.corp_id` 完全无校验。实现时如实保留，避免把"可选 im"误当"强校验"。

---

## 7. 参数↔config 映射（按命令面归类）

| 命令 | 涉及参数 | 写回 config.yaml？ | 触发 revalidate？ |
|---|---|---|---|
| `core-agent`（默认入口） | llm 4 + im 3 全局 flag | 否（运行态读取） | 启动时 schema 校验 |
| `core-agent serve --transport ...` | transport + MCP 端点参数 | 否 | 否 |
| `config show` | —（只读） | — | — |
| `config get <key>` | —（只读） | — | — |
| `config validate` | —（只读） | — | ✅ 触发 validate_schema |
| `config set <section>.<key>=<value>` | 任意可写键 | ✅ 写回 | ✅ 触发 revalidate（已实现：`write_patch` 写回后重读重校验） |
| `feature <name> on/off`（推演） | features 前缀 | ✅ 写回 features 段 | 否 |

---

## 8. 退出码 / 错误码基线

| 来源 | 内容 |
|---|---|
| MCP 错误码 8 项 | MCP_CONNECT_FAILED / MCP_PROTOCOL_MISMATCH / MCP_TOOL_NOT_FOUND / REMOTE_TIMEOUT / REMOTE_IRREVERSIBLE / PERMISSION_DENIED / MCP_UNAVAILABLE / TOOL_NAME_CONFLICT |
| 配置校验 | ValidationResult.errors 列表 |
| 健康探针 | probe exit 0=alive / 1=down |
| 缺 LLM 配置 | 阻断启动 |

---

## 9. 跨模块同名陷阱（落盘时须区分命名空间）

| 概念 | 语义1 | 语义2 | 定名方案 |
|---|---|---|---|
| budget | memory 检索 4096 | sandbox 资源 | `memory.read_budget` vs `sandbox.budget` |
| crystallize/dissolve | memory 事实 | skills 技能 | 前缀区分 |
| force | EvolutionTrigger.force | CLI --force | flag 化同一概念 |

---

## 10. 运行时命令面（UIAPILayer 9 方法 = 三桥统一命令面核心锚点）

| 类别 | 成员 | 暴露方式 |
|---|---|---|
| UIAPILayer 9 方法 | create_session / run_loop / barge_in / get_memory / compact / list_tools / invoke_tool / get_llm_config / set_llm_config | 三桥统一 API；create_session / run_loop 另经 CLI 子命令（session create / run）暴露，其余经 SSE/WS |
| 内置工具 tools.* | **实测 8 个**：file_read / file_write / file_patch / code_run / web_fetch（`tools/builtin.py`）+ install / uninstall / list（`tools/install_tools.py`）—— **均已实现**，与 `specs/tool-use` 一致。原列 web_scan / web_execute_js / ask_user / process / memory **在 src 与 specs 中零出现（从未存在）**，非承诺项（change `0056` 订正） | 工具 ID，经 ToolProvider.invoke 调用 |
| 对话指令 | SafetyGate.confirm(confirm/deny/auto) / ApprovalWorkflow.ask / tools.ask_user | 运行时交互，非 CLI |
| SSE 事件契约 | session.created / loop.perception / reasoning / action / result / error | Web/桌面流式协议，CLI 基线必选联动项 |
| 五阶段 loop | LoopPlugin.run/arun/astream + perceive/reason/act/observe/remember | 运行时协议，非 CLI |

---

## 11. 风险 / 待确认

1. ~~**CLI flag 层是否实现**~~ ✅ **已接线**：`_CONFIG_SPECS` 声明 `--llm.provider/model/endpoint/api-key/embedding-model`、`--im.gateway/corp-id/secret`、`--permission-mode`、`--pet-enabled/--pet-dir` 等（change `0056` 实测订正）。
2. **config set 写回 + revalidate**：~~写回是否会重跑 `validate_schema`，未确认。~~ ✅ 已确认：`write_patch` 写回后重读重校验（`apply_change` 先拒明文密钥，`${VAR}` 引用原样保留）。
3. ~~**secret 校验不对称**~~ ✅ **已修**（change `0056`）：`im.secret` / `judgment.api_key` 与 `llm.api_key` 同口径（非空 + 可解析）；详见 `specs/configuration`「密钥分级与安全」。
4. **features 无固定清单**（✅ 定性为**设计如此**，非缺口）：任意 `CORE_FEATURES_*` 可注册，CLI `--feature` 的补全/帮助无法静态枚举。
5. **extra 透传无校验**（🔶 **仍开放**：change `0056` 按用户裁决**未**收紧——收紧为白名单会拒绝既有自定义段、破坏既有部署；已转出为账本后续行，待定夺「仅告警」还是「硬拒」）。
6. **streamable-http transport**：= 账本 **B2**（需可选依赖 `mcp`，当前离线不可装）→ 见 `phase-19.md` §4。
7. ~~**permission-mode 枚举成员**~~ ✅ **已定并已强制**（change `0056`）：权限规格定为 read-only / interactive / auto-approve / high-risk-block 四档，配置校验期拒绝其他取值。

---

## 附：中间产出（可溯源）

- `temp/plan_cli_ops/prompt_step1.out.txt` — L0-L5 分层 + 已决策 + _ENV_OVERRIDES 实测
- `temp/plan_cli_ops/prompt_step2.out.txt` — 三模入口/生命周期/MCP/配置键/错误码/字段
- `temp/plan_cli_ops/prompt_step3.out.txt` — 增量 CMD/参数候选 46/30 项 + 关键结论 7 条
- `temp/plan_cli_ops/step4_cmd_list.md` — 命令面完整推演（29 动词 + 14 flag）
- `temp/plan_cli_ops/step5_param_map.md` — 参数↔config 映射敲定稿
