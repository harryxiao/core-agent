# TUI 斜杠命令：`/` 浮层补全（命令清单收敛为单一真源）

## Why

- **用户实测（2026-10-07）**：TUI 启动后输入 `/` **没有任何提示** —— 命令全靠记忆，无发现性。
  期望对齐 Claude Code：输入 `/` 弹出命令清单、键盘选择；对需要参数的命令再弹**二级**清单
  （如 `/focus` 列出当前子任务标识）；并要**内联幽灵补全**。
- **根因（实证）**：TUI 的斜杠命令**全部硬编码**在 `src/core/ui/repl.py` 的
  `ReplApp.on_input_submitted` 分支链里（`/task` `/focus` `/main` `/summon` `/recall` 共 5 个），
  **无命令注册表** ⇒ 既无「可枚举的命令清单」可呈现，也无「单一真源」可言（浮层与分发各记一份的隐患）。
- **规格缺口**：`ui` spec「CLI 友好交互」只要求终端交互能力（折叠块/流式/多面板/焦点），
  **未**约束「命令可发现」与「命令清单同源」。该缺口正是本缺陷得以存在的原因。

## What Changes

- `src/core/ui/repl.py`：
  - 模块级新增 **命令注册表**（`_Command` + `_COMMANDS`，单一真源：命令名 / 参数 / 说明）与
    **纯函数** `_palette_options(value, *, subtask_ids)`（一级按前缀筛命令；二级列枚举参数）。
  - `ReplApp`：`compose()` 增 `#palette`（`OptionList` 子类，**`can_focus=False`** —— 见风险①）；
    `CSS` 增浮层规则；`on_input_changed` 驱动开合与重筛；新增 `on_key` **仅在浮层呈现时**接管
    `↑`/`↓`/`Tab`/`Esc`；`on_input_submitted` 在审批分支之后插入**采纳即返回**（不提交）；
    `Input(suggester=…)` 接**内联幽灵补全**（与浮层候选**同源**）。
  - **分发链逐字保留**：既有分支与次序不动（`/focus`/`/main` 的忙态豁免、审批 y/n 语义、
    `/task` 的 `startswith("/task ")`、`/summon` 的 `_parse_beast_command` 全部原样）。
- `doc/openspec/specs/ui/spec.md`：「CLI 友好交互」**MODIFIED** —— 补「单一真源命令清单 + 浮层 +
  键盘采纳（只改写输入框、不提交）+ 二级枚举参数 + 审批期不呈现 + 幽灵补全」，**只增补**、
  既有 7 个 Scenario 措辞逐字不改；新增 6 个 Scenario。
- `doc/01-architecture/adr.md`：**ADR-0151**（`on_key` 接管 + `OptionList(can_focus=False)` +
  「注册表仅作呈现、分发链不动」）＋ 变更追踪行。
- `doc/03-interfaces/ui-interface.md` §2：补斜杠命令浮层与补全口径。
- `doc/04-testing/test-cases.md`：新增 `## 74.`（TC-CMDPAL）。
- `coding-plan/known-risk.md` §3：加 ADR-0151 局限行。

## Non-goals（明确不做）

- **不引三方库**；不引入 `Screen`/`ModalScreen`/`layers`/`push_screen`（沿仓库既有 `display`
  翻转惯用法，见 `_set_focus`）。
- **不改**现有命令的任何行为、提示串、分发次序；**不动**审批语义与 `/focus` 的忙态豁免。
- **不在本 change 做**会话切换（`/resume` 属 **0160**；此处**不**登记 `/resume`，否则会列出
  「采纳后无反应」的命令）。
- **不新增** api 方法（二级清单只用既有 `self._open` 的子任务标识）。
- 不做子串/模糊匹配（仅前缀，与幽灵补全同口径）；不做鼠标选择；不做「无匹配」占位。
- **不重写** `_BEAST_USAGE` / 各用法提示串为读表（那会改到多处以断言逐字为准的行；
  改用**可执行守护测试**绑定真源与分发）。

## 风险

- **风险①：`Tab` 不是空键**（实测，承重）：App 默认「焦点后移」在按 `Tab` 时把焦点从输入框移走；
  且声明 `BINDINGS` **无效**（默认焦点后移仍胜出）。⇒ 用 `on_key` + `prevent_default` 扣键，
  并给浮层 `can_focus=False`（双保险：即便漏掉某分支，`Tab` 也进不去浮层）。
- **风险②：唯一的**有意**行为变更**：输入是某命令的**严格前缀**（如 `/ta`）且用户按 `Enter` 时，
  采纳会把它补全为 `/task `（不提交），而**今天**它会作为普通消息进模型。⇒ 这是本需求的**目标面**，
  已在规格写明；非前缀的完整命令（`/main`）与未知前缀（`/zzz`）**命运不变**（有回归测试兜底）。
- **风险③：`Enter` 双触**（实测）：`on_key` 与 `Input.Submitted` **同触**，两处都写会**重复执行**。
  ⇒ `Enter` **只在** `on_input_submitted` 处理，`on_key` 对 `Enter` 显式放行。
- **风险④：审批期浮层遮蔽 y/n**：⇒ `_refresh_palette` 在审批挂起时直接收起，且 `_ask_approval`
  主动收起（有场景与测试守护）。
