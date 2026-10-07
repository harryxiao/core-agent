# 0163 · TUI 只读命令族（`/doctor` `/status` `/sessions` `/config` `/mcp` `/skill` `/notes`）

## Why

用户 2026-10-07 诉求（原话）：「指令回显对比 core-agent cmd 指令有 doctor,status,sessions,config,mcp,skill 等，
默认只装了四个，是否都可以支持下」。用户已确认口径：**「默认只装了四个」指的是 TUI 斜杠命令浮层这一面**，
范围是**只读 / 诊断类优先**。

现状：TUI 浮层（`src/core/ui/repl.py` 的 `_COMMANDS` 真源）只有 6 条命令
（`/task` `/focus` `/main` `/summon` `/recall` `/resume`）—— 运维与诊断类**一条都没有**；
而这些信息在 CLI 侧早已有实现（`config` / `mcp` / `skill` / `notes` / `sessions` 等 handler），
只是 TUI 端够不着。change `0162` 已把只读诊断源（`core/diagnostics`）建好，**本 change 是它的第二个消费面**。

## What Changes

- **命令真源增 `handler` 字段**（`_Command.handler: str = ""`）：命令名 → 处理器的对应关系**只此一份**
  （登记即接线）。`handler` 为空 ⇒ 走**既有专用分支链**（`/task` 等六条的行为**逐字不变**）。
- **新增 7 条只读命令**（`arg=""` ⇒ 无参数面）：`/doctor`（自检诊断）、`/status`（运行状态概览）、
  `/sessions`（会话清单）、`/config`（配置视图，密钥遮蔽）、`/mcp`（MCP 端点，**不出 `args`**）、
  `/skill`（技能目录）、`/notes`（笔记与常驻项）。
- **结果就地落一条时间线结果块**（`Report` → 逐行文本，`markup=False`）：**不进对话**（`run_loop` /
  `run_task` 不被调用）、**不产生 `❯` 回显**（与 `/focus` / `/main` / `/resume` 同侧）、**零副作用**
  （会话标识 / 转录 / 记忆 / 笔记 / 呈现态逐字不变）。
- **诊断源经 `UIAPILayer` 单一接缝注入**：新增 `diagnostics: Deps | None` 形参与 `diagnostics()` 访问器；
  `entry._build_ui`（**唯一**构造点，四入口共用）注入 `_diag_deps(args, tools=runtime.tools, config=...)`
  —— TUI 的「内置工具数」因此对**真实** `runtime.tools` 计数（与 CLI 的 builtin-only 面**有意不同**）。
- **守护扩展**：既有 `test_registry_commands_are_all_dispatchable`（「只登记、未接线即红」）**扩到全部
  13 条**；另加「每条 `handler` 都能在 app 上解析得到」（防登记名笔误）。

## Non-goals

- **不做写操作命令**（`config set` / `mcp add|remove` / `skill install|remove` / `plugin install`）——
  只读优先是用户拍板的口径。
- **不改**既有 6 条命令的语义、提示串、分发次序与审批语义（`/focus` 的忙态豁免**不动**）。
- **不动** Web / Desktop（命令面仍只属 TUI）；**不引三方库**；**不建**新数据源（全部复用 `0162` 的
  `Deps` 与既有 `UIAPILayer` 方法）。
- 扩展性**不做**：命令清单仍是**内存真源**（配置驱动 / 插件注册命令面属另一件事，另立 change）。

## 风险

1. **「登记与分发各记一份」退化**（0159 立此真源的初衷）：新增 7 条若只登记不接线，浮层可选但回车无声。
   ⇒ 由**可执行守护**兜底（真源每条命令的规范形态都必须被分发链消费）。
2. **忙态期插块**：只读命令若豁免忙态，会在流式写时间线的同时插块（与尾段渲染器互踩）。
   ⇒ 与 `/resume` 同侧：**排在忙态检查之后**，忙碌中拒绝。
3. **密钥泄漏**：`/config` 与 `/doctor` 直接呈现配置面 ⇒ 复用 `0162` 已收口的口径（只出 `${VAR}`
   引用名 + 布尔结论；`/mcp` 不出 `args`），并以哨兵值断言守护。
4. **`/sessions` 与 CLI `sessions` 同名异义**：CLI 的 `sessions` 列的是 Harness Host 连接记录，
   TUI 的 `/sessions` 列的是**会话注册表**（与 `/resume` 二级候选同源）⇒ 在规格、接口文档与 ADR 局限中
   **明写**，避免同名误读。
5. **浮层既有断言**：一级候选清单（`/` 全量、`/re` 前缀）与幽灵补全（`/re` → `/recall`）断言在案 ——
   7 条命令**追加在真源末位**、且无一命中 `/re` 前缀 ⇒ 既有断言**零回归**（除「全量清单」用例按新
   真源数更新）。
