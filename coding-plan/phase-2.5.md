# Phase 2.5 — 紧急补充（三方插件安装 + CLI 命令面契约回填）

> 里程碑：**无独立里程碑**（Phase 0/1/2 的增量补丁，Phase 3 开工前必须完成）
> 位置：补 Phase 0（plugin-registry / configuration）+ Phase 2（mcp / permission）；契约层另覆盖 Phase 1（tool-use）+ 新横切（cli-ops）
> 上游：Phase 0 + Phase 1 + Phase 2（全部已交付）
> 配套：`architecture-audit.md` + `architecture-adjustment-plan.md`（M1-M6 微调点原文）

---

## 1. 范围与定位

本 Phase **不是新能力主线**，而是对 Phase 0/1/2 已交付模块的**契约增量补丁**（来源：`architecture-adjustment-plan.md` 的 M1-M6）。交付两件事：

1. **契约定稿**：一次性落定 `0028-plugin-install` / `0029-cli-ops` 两个 change 的**全部** spec delta + ADR + interface（含 M3/M4 的契约，见 §2）。
2. **代码回填**：只实现 M1/M2/M5/M6（补 Phase 0/2 模块缺的部分）；M3/M4 的代码由 Phase 3 承接（契约已在本 Phase 定好，Phase 3 不重复改 spec）。

| 微调点 | 作用模块 | 模块归属 | 本 Phase 契约 | 本 Phase 代码 |
|---|---|---|---|---|
| M1 PluginSource 抽象 | plugin-registry | Phase 0 ✅ | ✅ | ✅ |
| M2 mcp add/remove | mcp | Phase 2 ✅ | ✅ | ✅ |
| M5 CLI 参数覆盖层 | configuration | Phase 0 ✅ | ✅ | ✅ |
| M6 permission-mode | permission | Phase 2 ✅ | ✅ | ✅ |
| M3 install/uninstall | tool-use | Phase 1（代码随 P3） | ✅ | ❌ → Phase 3 |
| M4 cli-ops | 新横切 | 无（代码随 P3） | ✅ | ❌ → Phase 3 |

> **为什么契约含 M3/M4、代码不含**：openspec change 是原子规格单元（一次 delta 双写 + 一次 ADR 追加，不可拆两次）；且 M3 契约依赖 M1 的 `PluginSource`、M4 契约依赖 M5 的 `ConfigSpec`，契约层强耦合必须一次锁死。代码实现按依赖分批：M3 端到端需 Phase 3 loop 驱动工具调用，M4 命令面需 M1/M2/M3 资产命令就位后收口，故代码随 Phase 3。

---

## 2. 契约定稿（openspec 0028 / 0029）

按 `openspec_sop` 落盘，**每个 change 三件套齐全**（无 `propose`，手工建 `changes/<id>/`）：`proposal.md` + `tasks.md` + `design.md` + `specs/` delta（L11）；delta 双写（change delta + `specs/<cap>/spec.md` 当前行为，L19/L21）+ ADR 追加（`adr.md` 全局递增）。**两个 change 一次性全量落定**。

> **openspec_sop 对齐红线（逐条，勿凭记忆）**：
> - **扩展既有 spec 改 Purpose 双向**（L22）：M1/M2/M3/M5/M6 均扩展已有 cap，`changes/<id>/specs/<cap>/spec.md` delta 与 `specs/<cap>/spec.md` 当前行为的 Purpose 都要反映新能力，再追加 Requirements；仅 M4 是全新 capability（双写，无「改 Purpose」）。
> - **数据结构属 how 不进 specs**（L29）：`InstallableAsset` / `PluginSource` 跨 M1/M2/M3 共享，收敛到 `doc/01-architecture/data-model.md` 单一权威索引（见 §2.1 第 6 项），spec Requirement 只写 what 语义。
> - **proposal What Changes 的 ADDED bullet 标题须与 delta「### Requirement:」需求名逐字一致**（L37）。
> - **proposal Affected docs 须列全所有实际改动文档**（L32）：以 git status 改动清单反向核对，见 §2.1 九项。
> - **validate 的 INFO/WARNING 每文件只报第一条**（L34）：归零须逐 change 全量 diff 同名 Requirement 正文（缺尾空行/缺 Scenario/缺实现行都算漂移），修复用 merged 正文覆盖 delta，**勿删 ADDED 段（会报 ERROR）**。

### 0028-plugin-install（M1 + M2 + M3）→ ADR-0037

| 子项 | 改哪 | 内容 |
|---|---|---|
| M1 | `openspec/specs/plugin-registry/spec.md` 扩展（改 Purpose 双向）+ 追加 Requirement「插件来源与安装」 | **what 语义**：系统 SHALL 支持四类来源（local-path / git-repo / market-registry / mcp-endpoint）安装插件，生命周期 discover→verify→install→register→activate→deactivate→uninstall；skillhub 签名校验/多源路由语义上提到此统一层。**数据结构（how）不写进 spec**，落 `doc/01-architecture/data-model.md`（§2.1 第 6 项） |
| M2 | `openspec/specs/mcp/spec.md` 扩展（改 Purpose 双向）+ 追加 Requirement「MCP Server 安装与移除」 | `mcp add/remove` 复用 `PluginSource(mcp-endpoint)`，install 后进入现有连接管理（连接/心跳/复用逻辑不改） |
| M3 | `openspec/specs/tool-use/spec.md` 扩展（改 Purpose 双向）+ 追加 Requirement「插件安装工具」 | `install / uninstall / list` 三工具，经 SafetyGate + 权限审批流约束（危险操作走审批） |

### 0029-cli-ops（M4 + M5 + M6）→ ADR-0038

| 子项 | 改哪 | 内容 |
|---|---|---|
| M4 | 新建 `openspec/specs/cli-ops/spec.md`（第 26 spec，双写）+ `03-interfaces/cli-ops-interface.md` | 命令集分组：生命周期 start/stop/restart/kill；状态 status/doctor/logs/version/help；资产 install/uninstall/list/info；连接 mcp add/remove/list；安全 auth/permission-mode；网关 gateway。参数映射优先级链 `CLI flag > env > config.yaml > 默认值`；`--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR` |
| M5 | `openspec/specs/configuration/spec.md` 扩展（改 Purpose 双向）+ 追加 Requirement「配置源与分层」 | 新增 CLI 覆盖层（最高优先级）；ConfigSpec 每项声明 `cli_flag / env_var / default / map_to`；CLI 暴露面按 core/advanced/hidden 分级（D5） |
| M6 | `openspec/specs/permission/spec.md` 扩展（改 Purpose 双向）+ 追加 Requirement「权限模式」 | `read-only / interactive / auto-approve / high-risk-block` 四档（D4），映射 `config.permission.mode`，CLI `--permission-mode` |

### 2.1 受影响文档（proposal Affected docs 逐项列全：路径 + 行号 + 改法）

> 以下九项须在 proposal Affected docs **列全**，并逐个落实；完成后用 `git status` 反向核对「列了且改了」双向闭合（L32/L35）。

| # | 文件（相对 `core-agent/`） | 修改点（行号以当前 HEAD 为准） | 改法 |
|---|---|---|---|
| 1 | `openspec/changes/0028-plugin-install/` | 新建目录 | `proposal.md` + `tasks.md` + `design.md` + `specs/{plugin-registry,mcp,tool-use}/spec.md` delta |
| 2 | `openspec/changes/0029-cli-ops/` | 新建目录 | `proposal.md` + `tasks.md` + `design.md` + `specs/{cli-ops,configuration,permission}/spec.md` delta |
| 3 | `openspec/specs/cli-ops/spec.md` | 新建（第 26 spec） | `# CLI Ops Specification` + `## Purpose` + `## Requirements`（无 ADDED，与 delta 双写，L19） |
| 4 | `doc/03-interfaces/cli-ops-interface.md` | 新建 | CLI 命令面/参数映射接口（照 durability 先例：独立横切能力 spec+interface 双文档，L25） |
| 5 | `doc/01-architecture/adr.md` | 追加 | ADR-0037（plugin-install）、ADR-0038（cli-ops），编号全局递增，勿与 change 编号 0028/0029 混用（L38） |
| 6 | `doc/01-architecture/data-model.md` | §2「横切（不属于任一层）」表（现 L99–111，durability 行后）追加一行 | 实体 `InstallableAsset / PluginSource`：语义=统一插件安装资产 / 来源枚举（kind∈skill\|mcp\|cli，source∈local-path\|git-repo\|market-registry\|mcp-endpoint，manifest，lifecycle）；权威定义=plugin-registry-interface.md。**M1/M2/M3 共享，spec 不写字段（L29）** |
| 7 | `doc/01-architecture/architecture-overview.md` | **6 处同步**（L35 实测易漏点） | ① L13 横切计数「5 个横切能力」→「6 个」，括号内加「CLI 运维」；② L44–45 ASCII 横切行：L45 追加 cli-ops（**长内容另起一行，勿顶破右边界 `│`，L36**）；③ L65–73 横切能力表追加一行「CLI 运维 cli-ops」；④ L79–99 核心组件表追加 CLI 组件行（接口文档填 `cli-ops-interface.md`）；⑤ L142–159 运行时视图 ASCII 横切组件区（L154–157 附近）追加 cli-ops 进程组件；⑥ L163–188 部署目录树横切目录区（L180–184 附近）追加 `cli-ops/` |
| 8 | `doc/00-product/requirements.md` | §1 功能需求清单，1.25 ci-cd（现 L260）后追加 | 新增「### 1.26 CLI 运维命令面（cli-ops）」，需求 ID 沿用 `CORE-CLIOPS-Rn`，追踪规格 `cli-ops/spec.md`（L26：specs 新增 capability 须同步 requirements 1.x 清单） |
| 9 | `doc/00-product/design-completeness-eval.md` | 五处数字 25→26（现 L5 / L18 / L22 / L24 / L114） | ① L5「补齐后为 **25 capability**（新增 …ci-cd）」→「26 capability」，括号末尾追加 `cli-ops`；② L18「25 模块 + 25 capability」→「26 模块 / 26 capability」；③ L22 标题「25 capability → 6 大功能域」→「26 capability」（标题也改）；④ L24「25 个 capability」→「26 个」；⑤ L114「六域 25 capability」→「六域 26 capability」。L6「17 capability 基线」是历史基线**不改**（L26 数字口径同步，漏一处即漂移） |

**契约影响面总览**：specs 25→26；interface 新增 cli-ops-interface.md；ADR 追加 ADR-0037/0038；data-model.md 横切表 +1 行；architecture-overview 6 处同步；requirements 1.x 追加 1.26；design-completeness-eval 数字 25→26。

---

## 3. 代码回填清单（M1 / M2 / M5 / M6）

> 仅实现下列四项；M3/M4 只落契约不写代码。

### 3.1 M1 — plugin-registry 统一安装抽象

- 数据模型：`InstallableAsset`（`kind / source / manifest / lifecycle` 字段）+ `PluginSource` 枚举（4 值）
- 生命周期接口：`discover() → verify() → install() → register() → activate() → deactivate() → uninstall()`
- 复用上提：skillhub 的签名校验 / 多源路由逻辑抽象为 registry 层的可复用原语（D3：registry 统一 + 执行层按 kind 适配，不合并执行实现）
- 错误码：`SOURCE_NOT_FOUND`、`SIGNATURE_INVALID`、`INSTALL_FAILED`（与 Phase 2 skillhub 语义对齐）

### 3.2 M5 — configuration CLI 覆盖层 + ConfigSpec 单一真源

- 优先级链：`CLI flag > env > config.yaml > 默认值`，CLI 覆盖层为最高优先级
- `ConfigSpec` 每项字段补 `cli_flag / env_var / default / map_to`（全量声明，D5）
- 暴露面分级：每项标注 `core / advanced / hidden`
- 单一真源校验：CLI flag / env / yml 三面由 ConfigSpec 生成，非法 `map_to` 阻断启动

### 3.3 M2 — mcp 安装/移除生命周期

- 实现 `mcp add(source)` / `mcp remove(name)`，复用 M1 的 `PluginSource(mcp-endpoint)`
- `add` 走 `discover → verify → install → register` 后进入现有连接管理（连接/心跳/复用逻辑不改）
- `remove` 走 `deactivate → uninstall`，释放连接资源

### 3.4 M6 — permission-mode 四档启动开关

- 实现 `read-only / interactive / auto-approve / high-risk-block` 四档（D4：四档先落地）
- 映射 `config.permission.mode` + CLI `--permission-mode`
- 危险 action 走配置层 spec 声明 `risk`；CLI 侧暂不加专用 flag（D4）

---

## 4. 依赖与前置

- **上游**：Phase 0（plugin-registry / configuration / observability）+ Phase 1（tool-use 的 ToolProvider/SafetyGate）+ Phase 2（mcp / permission），全部已交付。
- 关键前置：
  - M1 依赖 plugin-registry 已交付的 Plugin 基类与注册机制（Phase 0）。
  - M2 依赖 mcp 已交付的连接管理（Phase 2，连接/心跳/复用逻辑已闭环）。
  - M5 依赖 configuration 已交付的 yml 单一收口 + schema 校验（Phase 0）。
  - M6 依赖 permission 已交付的审批/拒绝链（Phase 2）。

---

## 5. 实现顺序

1. **契约定稿**（§2）：先落 0028/0029 全部 spec delta + ADR + interface，锁死契约，再动代码。
2. **M1**（registry 抽象，M2/M3 的共同地基）
3. **M5**（ConfigSpec 单一真源，M4 的映射模型依赖它）
4. **M2**（依赖 M1）
5. **M6**（依赖 M5 的 `permission.mode` 映射）
6. 门禁验收 → 提交

---

## 6. 契约对齐

以 `architecture-adjustment-plan.md` 的 M1-M6 为唯一微调基线；spec 落法以 `openspec_sop`（delta 双写 + ADR 追加）为准。

**契约红线**：
1. skillhub 现有 4 Requirement **不动**（D3，语义上提不合并执行实现）。
2. `InstallableAsset{kind}` 只做 registry 层统一，**不合并** skill/mcp/cli 的执行实现。
3. ConfigSpec 必须「全量声明」，CLI/env/yml 三面由 ConfigSpec 生成，禁止硬编码第二真源。
4. permission-mode 只落四档（D4），CLI 侧不加专用 flag。

---

## 7. 门禁验收

全局四命令（`ruff check` / `ruff format --check` / `pyright` / `pytest -q`）全部通过。

本 Phase 专属校验：

- [x] M1：`InstallableAsset{kind}` 三 kind 均可 discover→install→uninstall 闭环；签名校验失败拒绝 install；依赖环拒绝
- [x] M5：CLI > env > yml > 默认 优先级链正确；ConfigSpec 三面生成一致；非法 `map_to` 阻断启动
- [x] M2：`mcp add` 后进入现有连接管理并可用；`remove` 后连接资源释放
- [x] M6：四档 mode 生效；`read-only` 下写操作被拒；危险 action 声明 risk 后走审批
- [x] 契约：0028/0029 delta 双写完成，ADR-0037/0038 就位，specs 计数 25→26
- [x] 受影响文档九项闭合：overview 6 处同步、data-model 横切表 +1 行、requirements 1.26、design-eval 五处 25→26、cli-ops-interface.md 新建、ADR-0037/0038（`git status` 反向核对「列了且改了」双向闭合，L32）

---

## 8. 提交规范

- **一个 Phase 一个 commit**：契约 + 4 项回填 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase2.5): plugin-install/cli-ops 契约回填 M1/M2/M5/M6（0028/0029）`
- 提交后回填 `README.md` 新增 Phase 2.5 行状态。
