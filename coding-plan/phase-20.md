# Phase 20 — C 类「代码半」账本（真后端的可离线验证接线工程）

> **定位**：Phase 19 §5 把 `debug-gaps.md` §2.3 的 9 行**整块**记为「真实外部后端未接（低 / 需凭证）」，**未区分「凭证」与「接线」**。本文件对每行做**二分**：择出**代码半**（缺适配器实现 / 缺装配 / 缺 CLI 入口，且**可离线用 fake 验证**）单独记账；**凭证半**（真实平台 SDK / 网络 / 密钥）仍归 Phase 19，不在此重复。
> **基线**：`feat/phase0-base` @ `abba3d0`（change `0088` 归档后）；1030 tests 绿；`openspec validate --all` 29 specs 全绿、**无活跃变更**。
> **来源（2026-10-05）**：对 `src/` 的只读审计 —— 41 处「未接 / 待接入」措辞**逐处定性**，并与组合根（`runtime.py build_runtime`）＋ CLI（`entry.py`）核对「是否真的从未构造该组件」。
> **规则**：本 Phase 是**记账**不是**里程碑**；重开任一项按其所属 capability 走常规 SDD（spec delta → 测试 → 实现 → 四门 → 归档），并回填本表 + Phase 19 §5。

---

## 0. 结论

- **「未接」有两类，不可混算**：
  - **兜底文案**（非缺口）：`git/backend.py:50-55`、`ci_cd/pipeline.py:29-34`、`ci_cd/publisher.py:18-23`、`ui/desktop_bridge.py:33-34`、`mcp/transport.py:287-290`、`skillhub/client.py:51-58`、`plugin_registry/installable.py:59-61` —— 全是**依赖未注入时**抛出的结构化错误，写入的是「没接」这个事实，不是缺陷本身。反例已闭合：`beast/session.py:78-82`「记忆后端未接」是纯兜底（组合根恒注入 `memory`）。
  - **真缺口**（本文件主题）：`build_runtime` / `entry.py` **从未构造**该组件 —— `git` / `ci_cd` / `skillhub` / `IMGateway` 在组合根**零出现**（`grep -c` 全 0）。
- **8 项有可离线验证的代码半**：git、im、mcp transport（http 方向）、ui（TTS + Tauri 桌面壳）、observability、ci_cd、plugin_registry/plugins（多源 resolver）、skillhub。
- **凭证/网络/三方 SDK 只作为 4 项的「子项」存在**（im 平台 SDK、mcp http 的 `mcp` SDK、OTel 导出 SDK、技能市场 fetcher）—— 即「代码半做完后仍不可上生产」，但**做完的代码可离线用 fake 全部验证**。
- **1 行过时**：`pet / beast`（Phase 19 §5 沿 `debug-gaps.md` §2.3 抄录），其缺口已被 `0057` / `0079` / `0081` / `0083` / `0086` / `0087` / `0088` 关闭，见 §5。
- **无一项阻塞核心回路**（与 Phase 19 §0 同）。

---

## 1. 概览

| 项 | 模块 | 代码半（可离线验证） | 凭证半（阻塞，归 Phase 19 §5） | 优先级 |
|---|---|---|---|---|
| C2 | `git` | ✅ **已关闭（change `0090`／ADR-0085）**：`SubprocessGitBackend`（stdlib `subprocess` 直调 git CLI，13 原语）+ `build_backend()` 返回之 + 新增 `GIT_COMMAND_FAILED` + 错误不回显 stderr；**装配待消费者**（见 §4.1 偏离说明） | 无（git 是本地工具，**零凭证**） | ~~高~~ 已闭 |
| E27 | `im` | `IMGateway` 装配 + 宿主入口 + 白名单配置键 + Provider 插拔点 | 平台 SDK / 机器人凭证 / 回调 | **高**（第三入口整体缺席） |
| C3 | `ci_cd` | ✅ **已关闭（change `0091`／ADR-0086）**：`SubprocessGateExecutor`（stdlib `subprocess` 直跑 `GATE_COMMANDS`，不经 shell）+ 失败/工具缺失/超时归一 + `reason` 有界输出尾部；**装配与 `ci gate` CLI 待消费者**（见 §4.2 偏离说明） | 制品仓库凭证（`CHANNEL_UNREACHABLE`） | ~~中~~ 已闭 |
| C4 | `observability` | ✅ **已关闭（change `0089`／ADR-0084）**：组合根缺省装配 `BufferedExporter(JSONLExporter($CORE_STATE_DIR/traces.jsonl))` + 注入优先；`JSONLExporter` 自建父目录 | OTel 导出 SDK（「指标导出协议」，另案） | ~~中~~ 已闭 |
| C5 | `skillhub` | 把已实现的 `SkillHubClient` 接进 `skill search/install`（注入内存 `MarketIndex` 即离线可验） | 真实市场 fetcher（网络） | 中（客户端全实现却零调用方） |
| C6 | `plugin_registry` / `plugins` | `InstallDispatcher.resolve` 增补 GIT_REPO / MARKET_REGISTRY / MCP_ENDPOINT 三种来源 | git remote / 市场 / 端点可达性 | 中（`LOCAL_PATH` 已真） |
| C7 | `ui` TTS | TTS 接口 + 假实现 + 注入（现**无任何抽象**） | 真实 TTS 后端 | 低 |
| C8 | `ui` Tauri 桌面壳 | sidecar 拉起器（subprocess spawn）+ `_app` 注入 | Tauri 壳二进制 | 低 |
| B2 | `mcp transport`（http） | http/streamable-http Transport 适配器（`Mcp-Session-Id` 复用 + SSE 分帧） | `mcp` SDK 可安装（见 §3） | 低（stdio 已闭环） |

**已过时**：`pet` / `beast`（见 §5，不计入）。

---

## 2. E27：IM 网关（Phase 19 §3 E27 的代码半）

**现象（一手核实）**：IM 是本仓**三入口之一**（`doc/08-im-gateway/im-gateway.md` §2：人→CLI/Web/Desktop、机器→MCP Server、**随身→IM 网关**），但它是**唯一没有生产触达点**的入口：

- `IMGateway` 本体**齐备**（`register` / `on_message` / `reply` / `approve` + 白名单 + 幂等去重 + 会话映射 + 熔断隔离，`gateway.py`）；
- `IMProvider` 是 Protocol（`provider.py:19`），**零实现**；
- `IMGateway(...)` / `IMProvider` 在 `runtime.py` / `entry.py` **零构造、零注册**；
- CLI **无 `im` 子命令**（`entry.py` 的 parser 里没有）；
- 配置面**已有** `im.gateway` / `im.corp-id` / `im.secret`（`configuration/manager.py:64-88`、`models.py:46`，`gateway: feishu|wecom` 是平台选择器）——但**零运行时消费者**（只在 Configuration 内解析/校验/密钥引用校验）。
- 因此 `E27` 的「零生产装配」**不是「只差凭证」**：即使给了飞书凭证，也**没有任何代码会去读它**。

**代码半（可离线验证，用 fake Provider）**：

1. **装配**（组合根）：`build_runtime` 构造 `IMGateway(whitelist=…, run_session=…, confirm=…)` —— `run_session` 接到内核会话执行（同一 loop / 同一 permission 链路，规格「安全约束透传」要求不绕过）；`confirm` 接 `permission.ApprovalChannel`。
2. **宿主入口**（与 `ui serve` / `mcp serve` 对称）：`core-agent im serve` —— 按 `im.gateway` 选 Provider 并 `register` + `start()`；无 Provider 可注册时给结构化拒绝（不静默空转）。
3. **白名单配置键**：`im.whitelist`（当前**不存在**，只有构造函数参数）—— 新增须**规格先行**（`ConfigSpec` 单一真源 + `configuration` spec delta）。
4. **Provider 插拔点**：把 `IMProvider` 的发现/注册做成一处（模块路径或注册表），使「新增平台零侵入」（规格 R1）在**宿主侧**也成立。

**凭证半（归 Phase 19 §5，不在本文件）**：飞书长连接 WS / Telegram 长轮询 / 企业微信 等真实 Provider（规格「分平台接入」明文要求官方通道、禁用个人号）。

**建议**：**不单独立项**。代码半单独做完 = 一个**无平台可接的空接缝**（生产上没人往里发消息），与 Phase 19 反复记的「抽象已落地、缺生产触达点」同型却更贵（还多一个不可用的 CLI 入口）。建议**合并**：`im serve` + 装配 + **第一个真实 Provider**（飞书长连接 或 Telegram 长轮询，二选一）作为一个 change 做；`im.whitelist` 配置键随该 change 的 spec delta 一起落。

**转出**：pet 通知的「真实 IM 通道」（`0079` 留的 deferred 口）随本项一并解决 —— 届时把 `0079` 的缺省 stderr sink 换成注入的 `IMProvider` 即可，`PetSession._notifier` 注入面**不必改**。

---

## 3. B2 澄清：「懒依赖」是**懒 import**，不是**动态安装**

`B2`（远端 http/streamable-http 会话，Phase 19 §4）的依赖安排是 ADR-0043 的**按 transport 分流**：

- stdio（客户端本地 + 服务端本地）= **stdlib 手写**，零新依赖 —— **已落地**（`transport.py:163 StdioTransport`，真装于 `runtime.py:377` + `entry.py:592-594`）。
- http 远端 = `pyproject.toml` 的可选 extra **`core-agent[mcp]`** + `importlib.util.find_spec("mcp")` 检测；未装则抛 `MCP_CONNECT_FAILED` 并提示 `pip install core-agent[mcp]`（`transport.py:282-286`）。

**结论**：**没有动态安装，也不建议做**。当前实现是「**懒 import + 可选 extra + 缺 SDK 清晰降级**」，安装动作**由用户显式执行**（`pip install core-agent[mcp]`）。动态安装（运行期 `pip install`）会：① 违反 ADR-0044 立的「**核心零三方依赖**」红线口径（依赖面从「静态可审计」变成「运行期可变」）；② 在运行期执行第三方代码 —— 与 permission / sandbox 的 fail-closed 取向冲突；③ 让「装了哪个版本」不再可复现。

**B2 真正的剩余工作**是**代码**（不是打包）：用 `mcp` SDK 实现 http Transport 适配器（`Mcp-Session-Id` 复用 + SSE 分帧）并接进 `build_transport`；其**唯一硬前置**是「`mcp` SDK 在目标环境可安装」（ADR-0043 §后果已记：当前开发网络对包解析不可靠）。

---

## 4. C 类逐项（代码半）

> 每项给：**现状证据** / **要写的代码** / **离线验证手段**。全部沿用既有 DI 接缝，**不新增架构**。

### 4.1 `git`（C2）✅ 已关闭（change `0090`／ADR-0085）

- **现状（关闭前）**：`GitBackend` Protocol（`git/backend.py:18`）+ `GitClient` 只依赖注入 backend（`client.py:24-27`）；`build_backend` 抛「离线未接」；`runtime.py` / `entry.py` **零出现**。
- **已写**：`SubprocessGitBackend`（`src/core/git/subprocess_backend.py`）—— stdlib `subprocess` 直调 `git`，13 原语齐备（**零三方依赖**，gitpython/dulwich 未引入）；`build_backend()` 返回之；新增错误码 `GIT_COMMAND_FAILED`；`merge` 冲突走 `MergeResult(merged=False, …)`；错误**不回显** stderr（可能含凭据 / 私有仓库地址）。
- **离线验证**：`tests/test_git_subprocess.py`（9 例）在 `tmp_path` 临时仓库内走**真实 subprocess** 往返；`tests/test_git.py::test_default_backend_is_subprocess_adapter` 锁缺省工厂。
- **偏离原记（须记）**：本文件原计划的「**组合根装配 + `git` CLI 入口**」**有意不做** —— git 是 capability 非 tool（`git-architecture.md` §1），其消费者（coding 工作流）**尚未存在**；此刻塞进 `Runtime` 或加 `core-agent git <verb>` = **无消费者的空接缝**（与 §2 对 E27 的判定同理）。装配并入**消费者出现时**的该消费者 change。详见 change `0090` `proposal.md`「明确不做」。
- **仍归 Phase 19 §5（凭证半 / 可靠性半）**：远程凭据 keychain 集成（R3）、远程退避重试与连接释放（R5）。

### 4.2 `ci_cd`（C3）✅ 已关闭（change `0091`／ADR-0086）

- **现状（关闭前）**：`executor` / `channel` 均可注入（`pipeline.py:40-41`、`publisher.py:29-30`）；`GATE_COMMANDS`（ruff / pyright / pytest / uv build）**已定义**（`pipeline.py:21-26`）；`build_gate_executor` 抛「离线未接」；组合根零出现。注意 `release` CLI 子命令是 **Bundle 管理器**，**不是** ci_cd。
- **已写**：`SubprocessGateExecutor`（`src/core/ci_cd/pipeline.py`）—— stdlib `subprocess` 直跑 `GATE_COMMANDS`（`shlex.split`，不经 shell，零三方依赖）；`build_gate_executor(**kw)` 改工厂（`commands`/`cwd`/`timeout` 可注入）；**失败归一**为 `GateResult(passed=False)`（非零退出 / 工具缺失 / 超时），`reason` 含**有界**输出尾部（≤2000 字符，门禁输出是本地工具诊断文本、无凭据面 ⇒ **与 `0090` git「不回显 stderr」有意不同**）；未知门禁类型仍抛 `GATE_FAILED`（调用/配置错误）。`GATE_COMMANDS` 与既有测试零改动。
- **离线验证**：`tests/test_ci_cd_subprocess.py`（8 例）以 `sys.executable -c …` 注入命令走**真实 subprocess**（不依赖 PATH 上装了 ruff/pyright）。
- **偏离原记（须记）**：本文件原计划的「**组合根装配 + `ci/gate` 入口**」**有意不做** —— `ci_cd` 在 `src/` 内**零调用方**（消费者 = 尚未存在的交付编排）；且本仓四门可执行体**不在 PATH**（ruff 在 `~/.cache/uv/binaries-*`、pyright 在别的 venv、pytest 在 `.venv/bin`）⇒ 此刻上 CLI 等于给出一个**在本仓必然失败**的门面，`GATE_COMMANDS` 的 PATH/命令基准假设**本身需要一次决策**。装配与 CLI 并入消费者出现时的 change。
- **仍归 Phase 19 §5（凭证半）**：真实制品仓库通道（`publisher._default_channel` 保持抛 `CHANNEL_UNREACHABLE`）。

### 4.3 `observability`（C4）✅ 已关闭（change `0089`／ADR-0084）

- **现状**：`Exporter` Protocol + JSONL / Console / Noop / Buffered **均已实现**（`exporter.py:22-52`）；`Tracer()` 缺省 Noop（`tracer.py:24-26`），组合根 `runtime.py:224` **不传 exporter** ⇒ 生产**没有任何导出**。
- **要写**：`build_runtime` 一行装配（`Tracer(exporter=JSONLExporter/ConsoleExporter)`）；OTel 导出器是 `Exporter.emit` 的薄包装 + otel SDK（**凭证半**）。
- **离线验证**：断言 tracer 持有的 exporter 类型 + JSONL 落盘内容。

### 4.4 `skillhub`（C5）

- **现状**：`SkillHubClient` / `MarketIndex` / `TrustVerifier` / `SkillPublisher` **全部实现、DI 完整**（`client.py:20-58`、`index.py:27-35`）；但**零生产调用方** —— `entry._skill_search(SkillLibrary(), …)`（`entry.py:730-739`）走本地库，恒空。
- **要写**：把 `SkillHubClient` 接进 `skill search` / `skill install`；注入内存 `MarketIndex` 即可离线验证。真实市场拉取 fetcher = **凭证半**（网络）。
- **离线验证**：fake fetcher + 内存 index 的端到端。

### 4.5 `plugin_registry` / `plugins`（C6）

- **现状**：`PluginInstaller` 四钩子 DI + `InstallDispatcher` **已真装**（`runtime.py:378-381`，CLI `plugin install/list/uninstall` + `mcp add` 同一管线）；`LOCAL_PATH` **已真**（`install.py:48-55`）；余 `GIT_REPO` / `MARKET_REGISTRY` / `MCP_ENDPOINT` 三种来源抛「未接入 resolver」。
- **要写**：三种来源的解析器（clone / 市场 API / 端点安装）。
- **离线验证**：`LOCAL_PATH` 既有测试覆盖 + 三种来源用 fake 解析器。

### 4.6 `ui`（C7 TTS + C8 Tauri 桌面壳）

- **现状**：TTS **无任何抽象**（`api.py:111-113 barge_in` 抛 `UI_BARGEIN`、`repl.py:55-61` 降级兜底）；Desktop 有 `start_impl` 可注入（`desktop_bridge.py:23`）但 `_default_start` 抛错（`:33-34`），`entry.py:388-393` 的 `app` 分支未注入 ⇒ 未接。
- **要写**：TTS 接口 + 假实现 + 注入（可离线 fake）；sidecar 拉起器（`subprocess` spawn）+ `_app` 注入。
- **离线验证**：TTS 用假实现断言调用序；sidecar 用假可执行体（脚本）断言 spawn 参数。

### 4.7 `mcp transport` http（C9 = B2）

见 §3。

---

## 5. 已过时项：`pet` / `beast`

`debug-gaps.md` §2.3 的 `pet / beast` 行（Phase 19 §5 抄录）**已不适用**，其列出的缺口逐条已关闭：

| 该行列出的缺口 | 现状 | 关闭者 |
|---|---|---|
| 「loop 由宿主注入」 | 已装配（`runtime.py:694-724 _pet_loop` 专属 loop；`:748-759` 神兽） | `0081` / `0057` |
| 「通知通道」 | 已接通（生产者 `wake()` 收尾 + 缺省 stderr sink + 组合根收口 flush） | `0079` |
| 「宿主任期驱动」 | `core-agent pet run --interval`（`driver.py` + `entry.py:1266`） | `0083` |
| 「真实工具执行」 | 宠物专属 loop 的受限 `ToolProvider`（真工具 id） | `0081` |
| 「神兽 NL 提取」 | 启发式已接（`beast/activator.py:29-36`）；仅「Agent 深层意图」deferred | `0057` |
| — | 惊喜/微任务、控制面 | `0086` / `0087` / `0088` |

**残留三处（均不影响结论，登记于此以免再被抄录）**：

1. `pet/explore/explorer.py:32` 的 `run` 返回**假字符串**且**零生产调用方**（生产只用 `available()`；真实执行由 `0081` 的 `_pet_tools` 承担）—— 属**死代码**，非缺口。
2. 神兽「Agent 深层意图」提取仍是启发式（deferred，`0057` 已记）。
3. 通知的**真实 IM 通道**随 `im` 模块 deferred（并入 §2）。

---

## 6. 关闭判据

任一项标「已关闭」须同时满足：

1. 按 capability 走完 SDD（spec delta 先行 → 测试先行 → 实现 → 四门 → 归档）；
2. **离线可验证**：新增/修改的行为有**非凭证依赖**的测试锚点（fake 注入面）；
3. 回填 **三处账本**：本文件对应行、`phase-19.md` §1/§5 的 C 行、`coding-plan/README.md` §1/§2；
4. 若该项连带解决别的 deferred（如 §2 连带 `0079` 的真实 IM 通道），在**那边**也补一句「已由 change `<id>` 关闭」。

---

## 7. 关联

- `coding-plan/phase-19.md` §5（C 类总账，**凭证半**仍在彼处）
- `coding-plan/debug-gaps.md` §2.3（原始快照，**基线 `60d9724` @ 2026-10-01，已部分过期** —— 本文件是其代码半的订正与细化）
- `doc/01-architecture/adr.md`：ADR-0043（MCP SDK 依赖定位 —— §3 依据）、ADR-0044（核心零三方依赖 —— §3 依据）
- `doc/08-im-gateway/im-gateway.md` §2（三入口对称关系 —— §2 依据）、`doc/03-interfaces/im-interface.md`
