# Proposal 0237: 运行环境感知的 shell 方言（OS-aware code_run）

## Why

预置 prompt 与 `tools.code_run` 今日把「命令执行」默认成 **bash 心智**：

- `_SYSTEM_PROMPT` / 系统提示装配**不注入**宿主 OS、默认壳、路径风格；
- `code_run` schema 仅 `type ∈ {python, bash}`，实现硬编码 `bash -c`；
- TUI 把 `code_run` 一律渲染为 `Bash(...)`。

在 **Windows** 上这会导致：模型产出 POSIX/`&&`/`export`，执行面找不到 bash 或语法非法，
反复试错。对标 Claude Code（双工具 Bash/PowerShell + 平台选主壳）与 Cursor（Shell +
prompt 注入 `Shell: …`）的教训：**只改 prompt 不够，只改执行器也不够**——须「软事实 +
硬方言」同开。

本 change 落地调研结论的 **A+B / Phase 0→1**：系统提示注入运行环境事实；`code_run`
扩展 `powershell` 并按平台选默认方言；缺解释器 fail-closed。**不**拆 Claude 式双工具
（留给后续若权限规则变复杂再开）。

## What Changes

1. **运行环境探测**（纯函数、无副作用）：产出 `os` / `default_shell` / `shell_version`（可得时）/
   `path_style` / 简短禁忌提示；探测 `pwsh`/`powershell`/`bash` 是否在 PATH。
2. **Phase 0 — 系统提示块**：planner `_system_prompt` 增加独立块「运行环境」（非空才产块；
   测试可注入固定快照以保证确定性）。内容含 OS、默认壳、路径约定、与默认壳冲突的写法警示。
3. **Phase 1 — `code_run` 方言**：
   - schema：`type` ∈ `python | bash | powershell`（缺省：Darwin/Linux → `bash`，
     Windows → `powershell`；显式传入优先）；
   - 执行：`powershell` → `pwsh -NoProfile -Command`（回落 `powershell.exe`）；`bash` →
     既有 `bash -c`；`python` 不变；
   - 目标解释器不存在 ⇒ **结构化错误**，SHALL NOT 静默改方言；
   - 工具 description 写明三方言与平台默认。
4. **TUI**：活动标题按实际 `type` 显示 `PowerShell(...)` / `Bash(...)` / `Python(...)`，
   不再一律 Bash。
5. **规格**：loop ADDED「运行环境事实」；tool-use MODIFIED「内置原子工具」代码执行场景；
   ui 活动标题口径随 type（若落在既有 ui 需求则 MODIFIED，否则以 tasks 锚定实现）。

## Impact

- **规格**：`loop` / `tool-use`（+ 必要时 `ui`）delta。
- **代码**：探测模块（或 `tools`/`loop` 旁路小函数）、`planner.py`、`tools/builtin.py`、
  TUI 标题格式；测试。
- **兼容**：*nix + 显式/缺省 `bash` 与今日逐字等价；Windows 缺省从「假 bash」改为 powershell。
- **配置**：可选覆盖默认壳（设计钉死键名）；缺省不配 ⇒ 按平台表。

## Non-goals

- 真 **iOS** 本机 shell（本 change 的 Darwin 仅指 **macOS**）。
- Claude 式拆分 `shell_bash` / `shell_powershell` 两个 tool_id。
- CMD.exe 一等公民；沙箱/远程「执行面 OS ≠ 宿主 OS」（登记为后续候选）。
- Phase 2 失败回喂改写提示（可另开；本 change 只保证事实块 + 正确执行/拒执行）。
- 改变 `file_*` 优先于 shell 的产品策略（可在环境块中一句提醒，不强制）。

## Risks

- 模型仍写 bash：靠事实块 + description；若顽固，后续再加回喂（Phase 2）。
- Windows 无 `pwsh` 仅有 5.1：回落 `powershell.exe`，事实块尽量带版本，避免 7-only 语法。
- 有 Git Bash 的 Windows：默认仍 **powershell**（与 Claude「PS primary」对齐）；显式
  `type=bash` 才走 bash。
- 探测在 CI/无 PATH 环境波动：测试注入快照，生产探测失败 ⇒ 事实块降级为「OS + 未知壳」
  仍注入 OS，不阻断会话。
