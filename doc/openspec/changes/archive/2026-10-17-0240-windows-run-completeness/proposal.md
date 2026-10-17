# Proposal 0240: Windows 运行环境提示与 code_run 输出完整性

## 为什么

change `0237` 已让系统提示按宿主 OS 选择 shell 方言，但 Windows 实测仍出现两类问题：

1. **输出解码不确定**：`code_run` 用 `subprocess.run(text=True)`，解码依赖宿主 locale
   （zh-CN Windows 常为 cp936）；而 `pwsh` 7 通常输出 UTF-8、PowerShell 5.1 受
   `[Console]::OutputEncoding` 控制 ⇒ 中文输出乱码或被替换为 `�`，模型据此误判命令失败。
2. **提示事实不完整**：环境块只报默认壳，不报**实际可用**的 shell；默认壳解释器缺失时
   不给可执行的替代路径；未说明每次 `code_run` 是全新进程（`cd` / 环境变量不保留），
   也未给 `cwd` 的 `~` 语义；未知 OS 分支仍声称「默认壳为 bash」，与事实自相矛盾。
   模型因此在 Windows 上反复试错，最后回退到 `type=python` —— 回退本身合理，但应由
   提示**显式、有界**地给出，而不是被解码/事实错误逼出来。

此外，TUI / Web 在调用未显式给 `type` 时一律把 `code_run` 标成 Bash，Windows 上误导
操作者；`0237` 的 ADR D5 还记录了与生产代码不一致的快照注入说法。

## 做什么

- **P0 输出确定性**：`code_run` 的 stdout/stderr 固定按 UTF-8 解码（`errors="replace"`）；
  PowerShell 子进程执行前设置 UTF-8 输出编码；Python 子进程设 `PYTHONIOENCODING=utf-8`。
- **P0 提示事实**：环境块列出实际可用 shell（pwsh / powershell / bash），区分
  「PowerShell 7+ (`pwsh`)」与「Windows PowerShell 5.1 (`powershell`)」；默认壳不可用时
  明确建议 `type=python`；未知 OS 不再声称默认 bash。
- **P1 进程语义**：环境块声明每次 `code_run` 为全新进程，`cd` / 环境变量不跨调用保留，
  需指定目录用 `cwd`（绝对路径，支持 `~`）；`cwd` 在工具层做 `~` 展开。
- **P1 有界回退规则**：提示给出 Python 回退的适用边界（仅方言不可用或脚本无法用该方言
  表达时；用 `pathlib` / `tempfile`，勿硬编码 `/tmp`），避免把方言错误当成 Python 回退理由。
- **P1 活动标题**：TUI / Web 在未显式给 `type` 时按注入的**有效平台缺省**命名；事实不可得
  时用中性 `Shell`，SHALL NOT 谎报 Bash。
- **P2 文档纠偏**：工具 description 明示「显式 `type` 优先」；ADR-0227 D5 的「共享快照注入
  `code_run`」说法改为生产实际（每次调用重新探测）；接口文档补 `cwd` 展开与提示块条目。

## 不做什么

- 不改变「缺解释器 ⇒ 结构化拒绝、不静默改方言」的执行契约（Python 回退是**模型显式选择**，
  不是执行层自动降级）。
- 不引入 shell 版本探测子进程（标签按可执行文件名区分，避免启动期 spawn）。
- 不改变确认门、超时与截断口径；不新增配置键。

## 影响

- `src/core/tools/env_shell.py`、`src/core/tools/builtin.py`
- `src/core/runtime.py`（`Runtime.env_snapshot` 暴露给 UI）、`src/core/entry.py`
- `src/core/ui/api.py`、`src/core/ui/repl.py`
- `frontend/src/lib/activity.js`、`frontend/src/views/Chat.svelte`
- 规格：loop「运行环境事实」、tool-use「内置原子工具」、ui「code_run 活动标题按方言命名」
