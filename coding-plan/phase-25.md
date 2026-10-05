# Phase 25：插件安装链路「工具面闭环」缺口账本（E33 install 三工具零生产注册 + E34 CLIAdapter 声明不实 + E35 entry 安装链不齐 + E36 工具类安装不落盘）

> **定位**：本 Phase 是「插件安装」这条链路的**工具面闭环核查**账本 —— 与 `phase-24.md`（进化引擎内部核心插件）同批 review 产出，但主题不同：核查对象是 `core/plugins/`（安装执行层）↔ `core/tools/`（运行时工具面）↔ `core/entry.py`（CLI 入口）三处的**接线一致性**。四条均为**本次 review 一手复核新发现**，非此前 Phase 的转出账本（`phase-19/20/21/22/23/24` 均未列）。
>
> **来源**：本次 review 对 `install_tools.py` / `cli_adapter.py` / `entry.py` / `runtime.py` 实况复核，逐条回规格（`tool-use` / `mcp` / `plugin-registry` spec）核过判定归属。判据沿用本仓缺陷三分法：**「规格要求 X 而实现没有」= 真缺陷**；**「规格没要求、实现也没有」= 未接线/取舍（记账不报缺陷）**；**「实现即规格明文」= 不入账**。
>
> **去重口径（红线）**：`phase-20.md` 已列 E27（im）/ B2（mcp-http）/ C7（ui TTS）/ C8（ui Tauri）**不写**；`phase-22.md` 已修 observability/rag/skillhub **不写**；`phase-23.md` 缺口③（外部插件装载）已裁决「不修」**不写**；`phase-24.md` 已修 E30/E32 / 已裁决 E31 **不写**。**本 Phase 四条为插件安装链路专属新发现，与上述均无重叠**。

---

## 0. 结论总览

| 编号 | 缺陷 | 现状 | 归属 | 档位 | 建议 |
|---|---|---|---|---|---|
| E33 | `install_tools.py` 的 install/uninstall/list 三工具**零生产注册** | ✅ **已闭**（change `0108` / ADR-0101：组合根注册三工具 + 与 `Runtime.installer` 同实例 + 补对称 `uninstaller`） | tool-use 的**工具面闭环** | 中（对外能力缺口，规格承诺在生产不可达） | 组合根注册三工具 + 传 `Runtime.installer`（**要改代码，不需改规格**） |
| E34 | `CLIAdapter.adapt` 声明 `coeffects=[]`，实为 `subprocess` 真派生进程 | ✅ **已闭**（change `0108` / ADR-0101：声明改 `["process:spawn"]`） | tool-use 的**工具面安全**（确认门 + 默认暴露面） | 中 | `cli_adapter.py:75` 一行改 `["process:spawn"]`（**要改代码，不需改规格**） |
| E35 | `entry._plugin_install` 跳过 `verify`/`activate` 两步 | ✅ **已闭**（change `0108` / ADR-0101：补齐两步、与 `tools.install` 同链） | CLI 安装**链条完整性**（对照 `tools.install` 全链） | 低（今日净效果仅补齐链条） | 补两步（~2 行）；**用户裁决：补** |
| E36 | `plugin install --kind cli\|mcp` 安装结果**进程内即失**（不落盘） | ✅ **已闭**（change `0109` / ADR-0102：规格先行补「插件安装持久化」⇒ 账本 `plugin-installs.json` 落盘 + 按 `kind` 路由单一视图（mcp 委派端点表）+ 装配期重建） | 插件安装**持久化** | 低 | 已按「先补规格」实施（形状照 `mcp-endpoints.json` / ADR-0071） |
| — | 空 coeffect 工具进 MCP 默认暴露面（`tools.list` 等） | **已核实不入账**（`mcp/spec.md:104/:114` 规格明文） | — | — | **不改代码**；改判据须先改规格 |

> **共同口径**：E33/E34/E35 **同一主题**（插件安装链路的工具面闭环）—— 已按此**同一 change**（`0108` / ADR-0101）交付；E36 **单独立项**且**规格先行**（仍挂账）。四条均不挡核心回路（基础工具面与 M4 自进化已由 phase-16/18/21/24 打通），属**覆盖完整性**收敛。
>
> **耦合（关键）**：接线 **E33 会让 E34 变活** —— `runtime.py:461-463` 的 `InstallDispatcher` 持**生产** `ToolProvider`（`tool_provider=tools`，非一次性实例）。一旦经审批执行 `tools.install --kind cli`，`CLIAdapter` 产出的 `cli.*` 工具（今日 `coeffects=[]`）会注册进**生产工具面** ⇒ 同进程 `mcp serve` 的默认暴露面**默认放出**该工具。故 E33 与 E34 必须同批修，否则等于把「声明不实的派生进程能力」默认对外开放。

---

## 1. 缺陷清单

### 1.1 E33 install/uninstall/list 三工具零生产注册（规格承诺的对外能力不可达）

**现象**：`tool-use` 规格明文要求系统提供 `install`/`uninstall`/`list` 三个插件安装工具（使 Agent 可经对话/工具调用通道装卸插件），但**三个工具从未在组合根注册**——生产运行时工具面上不存在这三个工具。

**证据（行号）**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `doc/openspec/specs/tool-use/spec.md:91-108` | `### Requirement: 插件安装工具`：「系统 SHALL 提供 install / uninstall / list 三个工具，使 Agent 可经对话/工具调用通道安装、卸载、列出插件」+ 3 场景（对话安装 / 危险安装走审批 / 卸载与列出） | **规格明文要求**，3 条场景需有生产路径 |
| `src/core/runtime.py:360-362` | `builtin_tools = (file_read(), file_write(), file_patch(), code_run(), web_fetch())` → `tools.register(tool)` | 组合根只注册 5 个内置工具，**无 install/uninstall/list** |
| `src/core/runtime.py:690` | `tools.register(Tool(definition=ToolDef(tool_id="tools.delegate", ...)))` | 全组合根**仅此一处**额外注册（`tools.delegate`），仍无安装三工具 |
| `src/core/tools/install_tools.py:61/88/108` | `install_tool()` / `uninstall_tool()` / `list_tool()` | 三个工厂函数**零生产调用方**（全仓仅 `__init__` re-export 与单测调用） |
| `src/core/tools/install_tools.py:63/90/110` | `inst = installer if installer is not None else PluginInstaller()` | **缺省自造注册表**：即便被注册，若不注入真实 `installer`，也会操作一个一次性注册表（同 `entry._build_installer` 的一次性 `provider` 缺陷形态） |
| `src/core/pet/safety/safety.py:24-25` | `_DEFAULT_IRREVERSIBLE` 含 `"tools.install"` / `"tools.uninstall"` | pet 安全层**反向期待**这两个工具 id 存在（预设其已注册），实为悬空引用 |
| `tests/test_install_tools.py:10/18-40` | `from core.tools import install_tool, ...`；用**自造 installer** 测三工具 | 仅单测覆盖（注入式），**未覆盖组合根装配** |

**根因**：三个工具在 Phase 16（M3 插件/工具链路缺口）落地时只写了工具定义 + 注入式单测，**从未接进组合根装配**；`runtime.py` builder 只注册内置 5 工具与 `tools.delegate`，遗漏了这组工具。搭配 `install_tool` 缺省 `PluginInstaller()` 的自造形态，接线还须**注入** `Runtime.installer`（`runtime.py:464` 已构造、`:878` 已入 `Runtime` 字段），而非让工厂自造。

**后果**：规格承诺的「Agent 可经对话/工具调用通道安装、卸载、列出插件」**在生产不可达**，`tool-use` spec 的 3 条「插件安装工具」场景无生产路径。档位 **中**（对外能力的明文缺口，非内部死码）。

**登记源**：本 Phase review 新发现（规格 `tool-use/spec.md:91` ↔ 实现 `runtime.py:360-362` 对照）。

---

### 1.2 E34 `CLIAdapter` 声明 `coeffects=[]`，实为真派生进程（声明不实）

**现象**：`CLIAdapter.adapt` 产出的 `cli.*` 工具，`handler` 走 `subprocess.run` **真起子进程**，但 `ToolDef` 的 `coeffects` 声明为**空列表**——声明与行为不符。

**证据（行号）**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `src/core/plugins/cli_adapter.py:39` | `proc = subprocess.run(...)` | handler **真派生进程** |
| `src/core/plugins/cli_adapter.py:70-80` | `ToolDef(tool_id=f"cli.{name}", ..., coeffects=[], reversible=False, timeout_s=timeout_s)` | **声明零副作用**，与「派生进程」行为不符 |
| `src/core/tools/builtin.py:190` | `code_run` 声明 `coeffects=["process:spawn", "filesystem:write"]` | 同类能力（派生进程）的**规范声明口径** |
| `src/core/tools/safety_gate.py:38-40` | `_is_high_risk` 只匹配 `external` / `secret:` / `network:` | **`process:spawn` 不被判高危** ⇒ 见后果① |
| `doc/openspec/specs/mcp/spec.md:104` | 默认最小暴露 =「声明的 coeffect 集合为纯本地只读（`⊆ {"filesystem:read"}`；**未声明任何 coeffect 视为只读**）」 | **空集判为只读** ⇒ 见后果② |
| `doc/openspec/specs/tool-use/spec.md:29-40` | Requirement「coeffect 副作用契约」含弱场景「声明与行为不符告警」（记录偏差、标记待复核，**未规定观测机制**） | 规格承认该风险，但无强制补正机制 |

**根因**：Phase 16 CLI 适配层落地时按「最小可用」只补 `tool_id`/schema/超时，**coeffect 声明留空**（未对齐 `code_run` 的 `process:spawn` 口径）。

**后果**（两层，均因空声明）：
- ① **确认门不触发**：`SafetyGate.confirm` 对 `process:spawn` 不判高危（`_is_high_risk` 只认 external/secret/network）；`reversible=False` 的写类分支（`"write" in c`）亦不命中 ⇒ 派生进程**绕过审批**（fail-open）。**注**：即便补 `process:spawn`，SafetyGate 仍是原判据（不新增高危），此项**不由本修复关闭**，仅登记口径。
- ② **默认对外暴露**：MCP `_is_default_exposed` 判据 = `set(coeffects) <= {"filesystem:read"}`，**空集通过** ⇒ `coeffects=[]` 的 `cli.*` 工具**默认进对外暴露面**（把派生进程能力默认放出，与 B7/change 0076「跨边界能力默认不出」的收窄意图**相反**）。

档位 **中**（安全声明不实，且直接污染对外暴露面判据）。

**修复要点**：`cli_adapter.py:75` 空列表 → `["process:spawn"]`（对齐 `code_run` 的规范拼写）⇒ 后果②当即关闭。**红线权衡**：若一并加 `filesystem:write`（如 `code_run`），会因 `reversible=False` **新触发写类确认门**——本修复**只加 `process:spawn`**，不引入行为变更；`filesystem:write` 是否补另议（若补，须评估对既有 CLI 安装流程的审批打断）。

**登记源**：本 Phase review 新发现（`cli_adapter.py:70-80` ↔ `builtin.py:190` / `mcp/spec.md:104` 对照）。

---

### 1.3 E35 `entry._plugin_install` 跳过 `verify`/`activate`（CLI 安装链不齐）

**现象**：CLI `plugin install` 路径只走 `discover → install → register`，跳过 `verify`（签名校验）与 `activate`（激活）两步；而**同一安装生命周期的另一条调用路径**（`tools.install`）走全链。

**证据（行号）**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `src/core/plugin_registry/installable.py:4-5` | 模块 docstring：`discover → verify → install → register → activate → deactivate → uninstall` | 统一生命周期**声明为七步链** |
| `doc/openspec/specs/plugin-registry/spec.md:58` | Requirement「插件来源与安装」：「统一其生命周期：discover → **verify**（签名校验）→ install → register → **activate** → deactivate → uninstall」 | **规格明文**要求该链 |
| `src/core/entry.py:766-776` | `item = installer.discover(...)` → `installer.install(item)` → `installer.register(item, StubPlugin(...))` | **缺 `verify` 与 `activate`** 两步 |
| `src/core/tools/install_tools.py:68-73` | `discover → verify(asset, signature) → install → register → activate(plugin_id)` | 工具路径**走全链**（对照证据） |
| `src/core/entry.py:746-759` | `_build_installer` 未注入 `verifier`（`plugin_registry/installable.py:95` `self._verifier = verifier or _default_verify`） | 因未注入 verifier，`verify` 恒真、`activate` 只是状态翻转 ⇒ 今日净效果小 |

**根因**：CLI 路径按「最小落账本（register）」写就，未对齐 `installable` 声明与 spec 要求的完整链条。

**后果**：今日**净效果仅「链条不齐」**（`_default_verify` 恒真 + `activate` 状态翻转），**未造成可见故障**；但一旦注入真实 verifier（签名校验能力上线），CLI 路径将**静默跳过签名校验**，而工具路径不会——两条路径语义分叉。档位 **低**。

**待定性**：**是否补**由用户裁决（补齐 = 两路径语义一致；不补 = 承认 CLI 一次性进程无需 activate 状态机，但须在 spec/doc 诚实标注该取舍）。

**登记源**：本 Phase review 新发现（`entry.py:766-776` ↔ `install_tools.py:68-73` / `plugin-registry/spec.md:58` 对照）。

---

### 1.4 E36 `plugin install --kind cli|mcp` 安装结果进程内即失（未接线/取舍）

**现象**：CLI `plugin install --kind cli` / `--kind mcp` 安装成功后，结果**不落任何状态文件**，进程退出即消散；对照 `--kind skill` 因与组合根同源 `skills.json` 而**跨进程可见**。

**证据（行号）**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `src/core/entry.py:746-759` | `_build_installer` 每次新建 `_build_skill_library()` + **一次性** `ToolProvider()`（`:753`） | cli/mcp 工具注册进**一次性** provider，进程退出即散 |
| `src/core/entry.py:657-669` | 三处 CLI 入口（`install`/`list`/`uninstall`）各自 `_build_installer()` | 每次调用新建安装器，注册表亦为进程内 |
| `src/core/entry.py:749-750` | docstring：「技能库与组合根**同源**（`$CORE_STATE_DIR/skills.json`）——否则 `plugin install --kind skill` 装进一次性空库，**'已安装'是谎报**」 | **已为 skill** 解决跨进程可见（有先例） |
| `doc/openspec/specs/mcp/spec.md:173` | ：`mcp add` 的端点「SHALL **跨进程持久化**（`$CORE_STATE_DIR/mcp-endpoints.json`，原子写）」 | **mcp 端点有**持久化条款（change 0074 实现）；`plugin install` **无**对应条款 |

**根因**：`plugin-registry` / `tool-use` 规格**均无**「插件安装持久化」要求 ⇒ 属**未接线/取舍**（不是缺陷）。skill 类的跨进程可见是「与组合根同源库」的**副作用**，非持久化设计；cli/mcp 类无同源承载，遂进程内即失。

**后果**：`plugin install --kind cli|mcp` 装完即失（无可见故障，因该路径本就无消费方期待持久化）。档位 **低**。

**重开条件**：出现「插件安装持久化」规格条款时重开（形状可照 `mcp-endpoints.json` / change `0074`：状态非配置、原子写、装配期读回走同一安装管线）。**改代码前必须先写规格**。

**登记源**：本 Phase review 新发现（`entry.py:746-759` ↔ `mcp/spec.md:173` 对照）。

---

### 1.5 已核实不入账：空 coeffect 工具进 MCP 默认暴露面

**结论**：**不入账、不改代码**。理由：`mcp/spec.md:104` 明文「**未声明任何 coeffect 视为只读**」，`:114` 场景**明确期望** `tools.list`（未声明 coeffect）出现在默认暴露面内 —— 当前判据 `_is_default_exposed = set(coeffects) <= {"filesystem:read"}`（空集通过）**即规格明文行为**。`tools.list` 之所以声明为空，是其**确为只读**（列已装账本，无副作用），声明与行为**相符**（与 E34 的「声明不实」性质不同）。改判据（如要求显式声明）**须先改规格**，且会破坏 `:114` 既有期望。故本条**只作核查记录，不列缺陷**。

---

## 2. 修复方案

### 2.1 E33：组合根注册三工具 + 注入真实 installer

**目标**：让 `tools.install` / `tools.uninstall` / `tools.list` 在生产工具面可达，`tool-use` spec 的 3 条场景有生产路径。

**方案（供 claude code 参考，具体实现以代码实况为准）**：
1. 在组合根 `runtime.py` 注册三工具（`runtime.py:360-362` 内置工具注册同点或其后），工厂调用时**注入 `installer`**（`:464` 已构造、`:878` 已入 `Runtime`）——三工具须与 `Runtime.installer` **同一实例**，否则仍操作一次性注册表（`install_tools.py:63` 缺省自造形态）。
2. 注意**装配顺序**：`installer` 在 `:464` 才构造，而内置工具 `:360` 更早 ⇒ 三工具注册须排在 `installer` 构造**之后**（或延迟装配）；避免注册 `installer=None` 的自造形态。
3. `list` 工具声明 `coeffects=[]`（只读、`reversible=True`）本就正确；`install`/`uninstall` 声明 `["filesystem:write"]`、`reversible=False` —— 与 `pet/safety/safety.py:24-25` 的 `_DEFAULT_IRREVERSIBLE` 期待**对齐**（接线后该悬空引用自然落地）。
4. **无需改规格**（`tool-use/spec.md:91` 已要求三工具；安全姿态已写）。接线后须补**组合根装配**的集成测试（当前 `tests/test_install_tools.py` 仅注入式单测）。

**红线**：不让工厂自造 installer（必须注入 `Runtime.installer`）；不改三工具的 `tool_id` / schema；不新增 capability。

### 2.2 E34：`CLIAdapter` coeffect 声明补正

**目标**：让 `cli.*` 工具的声明与「真派生进程」行为一致 ⇒ 关闭「默认对外暴露」与「声明不实」。

**方案（供 claude code 参考，具体实现以代码实况为准）**：
1. `cli_adapter.py:75` `coeffects=[]` → `coeffects=["process:spawn"]`（对齐 `code_run`，`builtin.py:190` 规范拼写）。
2. 复核 MCP 默认暴露面：修复后 `{process:spawn} <= {filesystem:read}` 为假 ⇒ `cli.*` 工具**默认不暴露**（与 B7/change 0076 收窄口径一致）。
3. **无需改规格**（`tool-use/spec.md:29-40`「coeffect 副作用契约」已声明行为与 coeffect 对应；本修复使实现回归契约）。补单测断言 `cli.*` 工具 `coeffects == ["process:spawn"]`，且不进默认暴露面。
4. **权衡（必录）**：**不**顺带加 `filesystem:write`——否则因 `reversible=False` 新触发写类确认门，改变既有 CLI 安装流程的审批行为。是否补 `filesystem:write` 属**另一议题**（须评估与 E33 接线的交互）。

**红线**：只改声明、不改 behavior（handler 不动）；不加 `filesystem:write`（除非另行裁决）；不改 MCP 判据本身。

### 2.3 E35：`entry._plugin_install` 补齐 `verify`/`activate`（**待裁决**）

**目标**：CLI 路径与工具路径语义一致（同一生命周期七步链）。

**方案（供 claude code 参考，具体实现以代码实况为准）**：
1. `entry.py:766-776` 在 `install(item)` 前补 `installer.verify(item, str(item.manifest.get("signature", "")))`，在 `register(...)` 后补 `installer.activate(plugin_id)`（照 `install_tools.py:68-73`）。
2. 若裁决**不补**：在 `entry.py` / `plugin-registry` 接口文档**诚实标注**「CLI 一次性进程不承载 activate 状态机」的取舍，不虚假宣称链条完备。

**红线**：**先由用户裁决**（补 / 不补）；不擅自扩大改动面；不引入 verifier 注入（除非另行裁决）。

### 2.4 E36：工具类安装持久化（**规格先行，单独立项**）

**目标**：`plugin install --kind cli|mcp` 跨进程可见（**仅在补规格后**）。

**方案（供 claude code 参考，具体实现以代码实况为准）**：
1. **第一步（规格）**：在 `plugin-registry`（或 `tool-use`）spec 补「插件安装持久化」Requirement —— 安装记录落 `$CORE_STATE_DIR`（形状照 `mcp-endpoints.json`：状态非配置、原子写、装配期读回走同一安装管线）。
2. **第二步（实现）**：CLI `plugin install` 落盘 + `_build_installer` 读回；与 `mcp add`（change 0074）复用同一持久化范式。
3. **本 Phase 不做**，只登记重开条件。

**红线**：**规格先行**（无规格条款前不动代码）；不与 E33 同 change（避免混入未裁决的持久化语义）。

---

## 3. 验收清单

- [x] ① `tools.install` / `tools.uninstall` / `tools.list` 在生产工具面可见（组合根装配后 `tools.active_tools()` 含三者）。
- [x] ② 三工具与 `Runtime.installer` **同一实例**（非自造注册表）；**连带补 `uninstaller=dispatcher.uninstall`**（原 `Runtime.installer` 只注入 `resolve`+`install`，`tools.uninstall` 无法 kind 分发回退）—— 超出原判定的增量，见 §6。
- [x] ③ `cli.*` 工具 `coeffects == ["process:spawn"]`；不进 MCP 默认暴露面。
- [x] ④ `pet/safety/safety.py:24-25` 的 `tools.install`/`tools.uninstall` 引用不再悬空（有对应已注册工具）。
- [x] ⑤ E35 **按用户裁决补齐** `verify`/`activate`（与 `tools.install` 同链）。
- [x] ⑥ E36 **已闭**（change `0109` / ADR-0102：账本落盘 + 按 `kind` 路由单一视图 + 装配期重建；规格 ADDED
      「插件安装持久化」7 场景）—— **原「E36 未动代码」判据由本 change 取代**，见 §7。
- [x] ⑦ 未改 `tool-use` / `mcp` / `plugin-registry` 规格（`skip_specs`；**change `0108`** 规格中性）。
- [x] ⑧ 门禁四件套全绿：`ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest`（1248 passed）。
- [x] ⑨ `openspec validate --all` 全绿（30 passed / 0 failed）。

**E36 / change `0109` 追加**（原 §2.4 判「规格先行、单独立项」已执行）：

- [x] ⑩ 规格先行：`plugin-registry` **ADDED**「插件安装持久化」（7 场景：跨进程可见 / 装配期重建 / mcp 委派 /
      卸载对称回退 / 未安装卸载 / 账本损坏降级 / 重建失败不阻断装配）。
- [x] ⑪ 一口径裁决（用户，2026-10-05）：**mcp 真源 = 委派端点表**（不统一收敛）+ **装配期 = 重建物化**
      （不「只让 `list` 说得出口」，否则谎报）。
- [x] ⑫ 端到端（真实子进程）：`plugin install --kind cli` → **新进程** `plugin list` 命中 → `plugin uninstall`
      成功且账本清空；`plugin install --kind mcp` 落 `mcp-endpoints.json` 而**本账本不含**。
- [x] ⑬ 门禁四件套全绿：`ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest`（**1272 passed**，
      较 1248 +24 新例）；`openspec validate --all` 30 passed / 0 failed。

---

## 4. 契约对齐

- **E33/E34 属既有契约的接线收尾**：`tool-use` spec 已要求三工具（`:91`）、已声明 coeffect 与行为对应（`:29-40`）⇒ **无需 spec delta**，仅补实现与集成测试。
- **E35 若补**：`plugin-registry` spec `:58` 已要求七步链 ⇒ 亦是回归契约，无需 delta；**若不补**，须在接口文档诚实标注取舍（**可能**触发文档订正，不触发 spec 变更）。
- **E36 若做**：**必须 spec delta 先行**（新增「插件安装持久化」Requirement），且新增 ADR 记录持久化口径（形状参照 change 0074 `mcp-endpoints.json` / ADR-0071）。
- 相关 ADR 参照：ADR-0073（B7 默认暴露面收窄 —— E34 的对外暴露面口径依据）、ADR-0071（`mcp-endpoints.json` 持久化范式 —— E36 形状依据）。E33/E34/E35 若同批落地，**新增一条 ADR** 记录「插件安装链路工具面闭环」的接线口径与 E35 裁决。

---

## 5. 门禁与红线

- **红线**：E33 必须注入 `Runtime.installer`（同一实例），**不得**让 `install_tools` 工厂自造注册表（否则接线后仍是「装进一次性库」的谎报）。
- **红线**：E34 只改声明、不改 handler 行为；**不**顺带加 `filesystem:write`（避免行为变更）。
- **红线**：E35 **待用户裁决**，不擅自补/不补；E36 **规格先行**，无 spec 条款前不动代码。
- **红线**：不重复 phase-20（E27/B2/C7/C8）、phase-22（observability/rag/skillhub）、phase-23（缺口③）、phase-24（E30/E31/E32）已列/已修/已裁决项。
- **门禁**：提交前四件套全绿；一个 Phase 一个 commit；更新 `README.md` §1 文档清单与 §2 Phase 总览表。

---

## 6. 收口（change `0108` / ADR-0101）

**交付**：`doc/openspec/changes/archive/2026-10-05-0108-plugin-install-tool-face-wiring/` —— **规格中性**
（`.openspec.yaml` 置 `skip_specs: true`），无 spec delta；`tool-use` / `plugin-registry` / `mcp` 三 spec
**零改动**（本 change 是实现回归既有契约）。

| 缺陷 | 落地 | 证据 |
|---|---|---|
| E33 | 组合根注册三工具（`install_tool(installer)` / `uninstall_tool(installer)` / `list_tool(installer)`，排在 `installer` 构造后）；**连带补 `uninstaller=dispatcher.uninstall`**；三工具 `coeffects` / `reversible` 不变（写 + 不可逆仍走确认门） | `tests/test_install_tools.py` +3 例；`tests/test_phase13.py` 精确集合补 3 id |
| E34 | `cli_adapter.py` 声明 `[]` → `["process:spawn"]`（只改声明、不改 handler；**不加 `filesystem:write`**） | `tests/test_phase16.py::test_cli_adapter_declares_process_spawn`（+3 例 resolver 注入） |
| E35 | `entry._plugin_install` 在 `install` 前补 `verify`、`register` 后补 `activate` | `tests/test_entry.py::test_plugin_install_runs_full_lifecycle` |
| — | E36 **未动**（登记重开条件） | — |

**门禁**：`ruff check` / `ruff format --check` / `pyright`（0 errors, 0 warnings）/ `pytest`（**1248 passed**，
较此前 1243 +5 新例）四门全绿；`openspec validate --all` 30 passed / 0 failed。

**超出原判定的增量（如实登记）**：接线 E33 时发现 `Runtime.installer` **只注入了 `source_resolver` +
`installer`、漏注入 `uninstaller`**（`record` 面 `entry._build_installer` 有、组合根无）⇒ 若只注册三工具而不补
`uninstaller`，`tools.uninstall` 会「摘账本但不做 kind 分发回退」（skill 移除 / cli·mcp 工具摘除）—— 是**半接线**。
故同批补 `uninstaller=dispatcher.uninstall`（1 行）。原 §2.1 方案未列此项，此处订正。

**未做（明示）**：E36（`plugin install --kind cli|mcp` 持久化）—— 规格无持久化条款，须**规格先行**、单独立项
（形状可照 `mcp-endpoints.json` / change `0074`）。 ⇒ **已由 change `0109` 执行**，见 §7。

---

## 7. 收口（change `0109` / ADR-0102：E36）

**交付**：`doc/openspec/changes/archive/2026-10-05-0109-plugin-install-persistence/` —— **非规格中性**：
`plugin-registry` **ADDED**「插件安装持久化」（单项 Requirement / 7 场景）。

**一手复核订正（§1.4 记载的缺口范围偏窄）**：改前实测（`/tmp/e36`，真实进程）缺口**不限于 cli/mcp 的物化**：

| 操作（跨进程） | 改前实际 | 证据 |
|---|---|---|
| `plugin install --kind skill` | ✅ 写 `skills.json` | 仅**物化**落盘，账本仍空 |
| `plugin install --kind cli` | ✅ rc 0 但**一个字节都不落盘** | 状态目录只有 `skills.json` |
| `plugin list` | ❌ 恒「（无已安装资产）」 | `PluginInstaller._assets` 是**进程内字典** |
| `plugin uninstall <id>` | ❌ 恒 `UNINSTALL_NOT_FOUND` | 同上 |

即 **安装账本整体不落盘** ⇒ `list` / `uninstall` 对**所有** kind 都跨进程失效（skill 只是「物化」侥幸落盘）。

| 面 | 落地 | 证据 |
|---|---|---|
| 账本 | `plugins/installs.py`：`plugin-installs.json`（`$CORE_STATE_DIR`，单文件 JSON + `version` + **原子写** + 损坏/残缺 `warn` 降级） | `tests/test_plugin_installs.py`（20 例，含 `::test_interrupted_write_keeps_previous_file`） |
| 路由 | `PluginInstallStore`：`kind=mcp` → `MCPEndpointRegistry`（委派，`put()` upsert）；其余 → 本账本；`records()` **合并单一视图** | `::test_store_routes_mcp_to_endpoint_registry`（断言本账本**不含**）+ `::test_store_records_merges_both_views` |
| 写点 | `PluginInstaller(store=…)`：`register` → `put`（**先落盘再入内存**）/ `uninstall` → `remove`（**物化回退成功才清账**）/ 构造期水合 | `::test_installer_register_persists` / `::test_installer_hydrates_from_store` / `::test_installer_uninstall_clears_ledger` |
| 装配 | `build_runtime` 在端点循环后读账本逐条 `dispatcher.install`，单条失败**只告警跳过** | `tests/test_install_tools.py::test_runtime_rebuilds_cli_install_from_ledger` / `::test_runtime_skips_unrebuildable_record` |
| 幂等 | `plugins/install.py` `_uninstall_skill` 容忍技能已不在（账本条目可能陈旧 ⇒ 裸 `KeyError` 本 change 后可达） | `::test_uninstall_skill_is_idempotent_when_absent` / `::test_uninstall_cli_tool_is_idempotent` |
| 端到端 | CLI 三入口**零改动**（经 store 自动一致）——`plugin install --kind cli` 跨进程可见 | `tests/test_entry.py::test_plugin_install_persists_across_processes` / `tests/test_mcp_endpoints.py::test_cli_plugin_install_mcp_delegates_to_endpoints` |

**门禁**：`ruff check` / `ruff format --check` / `pyright`（0 errors, 0 warnings）/ `pytest`（**1272 passed**，
较此前 1248 +24 新例）四门全绿；`openspec validate --all` 30 passed / 0 failed。

**已知局限（如实登记）**：①`installed()` 读**构造期水合的内存副本** ⇒ 同进程**运行中**别处新装的不可见
（跨进程可见性的口径是「新进程读盘」，同端点表）；②mcp 类资产的账本身份**即端点名**（`plugin_id` 与 manifest
`name` 不一时以端点名为准）；③`plugin install --kind mcp` 走的仍是 `_build_installer` 的**裸** `MCPClient`
（无沙箱策略），而 `mcp add` 用 `host_allowlist` fail-closed 策略 —— 属 **E36 之外的既有面**，本 change 未动，**登记**待议。

**未做（明示）**：**不**把 `mcp-endpoints.json` 并入本账本；**不**改 `mcp add|list|remove` 的 CLI 语义
（重名仍拒绝、仍先握手再落盘）；**不**新增 capability、**不**改 `PluginInstaller` 既有公开签名（只加可选 `store=`）。
