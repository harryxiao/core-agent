# Design 0240: Windows 运行环境提示与 code_run 输出完整性

## 背景

`0237`（ADR-0227）已把 OS / 默认壳探测接入 planner 与 `code_run`。复盘 Windows 实测失败后，
确认根因不在「有没有 OS 感知」，而在三处细节：

- **解码**：`subprocess.run(..., text=True)` 按 `locale.getpreferredencoding()` 解码。zh-CN
  Windows 上是 cp936，而 `pwsh` 7 默认 UTF-8 ⇒ 中文乱码；5.1 的输出编码又由
  `[Console]::OutputEncoding` 决定 ⇒ 同一段脚本在不同 Windows 上表现不一致。
- **事实**：环境块只给默认壳，隐藏了 `has_bash` 等可用性；默认壳缺失时模型没有确定的下一步；
  未知 OS 走 `else` 分支却输出「默认壳为 bash」。
- **呈现**：`_code_run_name` / `activity.js` 在 `type` 缺省时写死 `bash` ⇒ Windows 的活动标题
  谎报 Bash。

## 决策

### D1 stdout/stderr 固定 UTF-8 解码

`subprocess.run` 增 `encoding="utf-8", errors="replace"`。理由：解码必须在**父进程侧**确定，
不能依赖子进程 locale；`errors="replace"` 保证任何字节流都返回字符串（不抛
`UnicodeDecodeError`），最坏情况是可辨识的替换符而非整条工具失败。

### D2 子进程侧 UTF-8 输出

- **powershell**：在用户脚本前拼接**有界 preamble**：
  `[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; $OutputEncoding = [Console]::OutputEncoding`。
  `New-Object System.Text.UTF8Encoding $false` 在 5.1 与 7+ 均可用；不改 `$PSDefaultParameterValues`
  等全局状态，避免影响脚本语义。preflight 失败会作为脚本错误返回，不会被静默吞掉。
- **python**：子进程 env 增 `PYTHONIOENCODING=utf-8`（保留其余 `os.environ`）。这样
  `print("中文")` 在 cp936 控制台/管道下仍输出 UTF-8，与 D1 的父侧解码配对。

只对 `code_run` 自身拉起的子进程生效；不修改宿主环境。

### D3 环境块：可用性、版本标签、缺失默认壳、进程语义、回退边界

`format_env_block` 保持有界（每行一句话），新增：

- `可用 shell：…` 列 PATH 上实际存在的 `pwsh` / `powershell` / `bash`；全无时写「未检测到」。
- 标签区分 `PowerShell 7+ (pwsh)` 与 `Windows PowerShell 5.1 (powershell)`（按可执行文件名，
  不起版本探测子进程）。
- 默认壳不可用 ⇒ 明确一行「改用 `type=python`（当前解释器始终可用）」。
- 每次调用为**全新进程**；`cd` / 环境变量不跨调用保留；需目录用 `cwd`（绝对路径，支持 `~`）。
- Python 回退**有界**：仅在方言不可用或脚本无法用该方言表达时；用 `pathlib` / `tempfile`
  等标准库，勿硬编码 `/tmp`；不得用 Python 回退掩盖方言错误。
- 未知 OS 分支只陈述「默认 shell 未知，建议显式 `type`」，不再声称 bash。

**不自动回退**：`resolve_run_type` 仍按平台缺省返回 powershell/bash；缺解释器由 `shell_argv`
结构化拒绝。回退是模型在提示指导下**显式**选择 `type=python`，保持 tool-use「缺解释器不得
改方言」的契约。

### D4 活动标题使用有效 type

- `_code_run_name(args, default_shell)`：显式 type 优先；缺省时按注入的 `default_shell`
  （powershell→PowerShell，bash→Bash）；事实不可得（None / unknown）⇒ 中性 `Shell`。
- `UIAPILayer` 增可选 `env_snapshot` 注入与 `default_shell` 属性；`_build_ui` 传
  `runtime.env_snapshot`，`Runtime` 增 `env_snapshot` 字段（与 planner 共用同一份探测结果）。
- TUI 的 `_add_action_widget` / `_progress_subtask` 与 CLI `_stream` 把该值传给
  `format_action_event(..., default_shell=…)`。
- Web 无运行时事实注入 ⇒ `toolName(toolId, args)` 对 `code_run`：显式 type 命名，
  否则 `Shell`；`Chat.svelte` 在 `startAction` 时把友好名存进时间线项，避免渲染时丢 args。

### D5 文档纠偏

- ADR-0227 D5 原写「生产 `code_run` 注入共享快照」与代码不符：`builtin_tools()` 不接收快照，
  `code_run` 每次调用 `probe_environment()`。本 change 在 ADR-0228 明确生产语义为**每调用
  重新探测**（PATH 变化即时可见；planner/TUI 用启动快照），不改执行代码。
- 工具 description 与 schema 补「显式 `type` 优先于平台缺省」「`cwd` 支持 `~`」。
- `doc/03-interfaces/prompts.md` 的动态块表补「运行环境」块（0237 遗漏）；
  `tool-use-interface.md` 撤掉「`code_run` 的 `cwd` 未纳入 `~` 展开」的登记。

## 改动面

| 文件 | 改动 |
|---|---|
| `src/core/tools/env_shell.py` | 标签 / 可用性 / 缺失默认壳 / 进程语义 / 回退边界 / 未知 OS 分支 |
| `src/core/tools/builtin.py` | UTF-8 解码、PowerShell preamble、Python env、`cwd` `~` 展开、schema/description |
| `src/core/runtime.py` | `Runtime.env_snapshot` 字段并传入构造 |
| `src/core/entry.py` | `UIAPILayer(env_snapshot=…)`；CLI 动作行传 `default_shell` |
| `src/core/ui/api.py` | 可选 `env_snapshot` + `default_shell` 属性 |
| `src/core/ui/repl.py` | `_code_run_name` / `_tool_name` / `format_action_event` 的有效 type；调用点接线 |
| `frontend/src/lib/activity.js` + `activity.test.js` | `code_run` 按 type 命名；缺省 `Shell`；符号 |
| `frontend/src/views/Chat.svelte` | 时间线项存友好名并用于 summary |
| 规格三份 | 见 `specs/` |

## 测试与反证

- 环境块：可用 shell 列表、版本标签、默认壳缺失建议 python、未知 OS 不称 bash、
  全新进程 + `cwd` + `~` + 回退边界。
- `code_run`：捕获 `subprocess.run` kwargs —— `encoding="utf-8"` / `errors="replace"`；
  python env `PYTHONIOENCODING=utf-8`；powershell argv 含 UTF-8 preamble 且保留用户脚本；
  `cwd="~/x"` 展开为家目录。
- 标题：TUI `_tool_name` / `format_action_event` 在 `default_shell=powershell|bash|None`
  下分别 PowerShell / Bash / Shell；既有「缺省=bash」断言改为中性 `Shell`。
- Web：`toolName("tools.code_run", {type})` 三档 + 缺省 `Shell`；`titleFromAction` 同名。
- **反证**：摘掉 `encoding`/preamble/`default_shell` 接线 ⇒ 对应用例红；复原后 `md5sum` 同。

## 局限

① 不起子进程探测 PowerShell 主次版本，标签只到「7+ / 5.1」这一可执行名粒度；
② `errors="replace"` 对真正非 UTF-8 输出的字节不可逆（可辨识但不还原原文）；
③ Web 端无环境事实注入，缺省只能中性 `Shell`（不猜测平台）；
④ 生产 `code_run` 仍每调用探测 PATH，与 planner/TUI 的启动快照在极端 PATH 变化下可能
短暂不一致（见 D5，属既定取舍）。
