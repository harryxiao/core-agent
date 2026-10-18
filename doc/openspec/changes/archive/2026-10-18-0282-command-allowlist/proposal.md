# 0282 — auto-approve 命令模式级允许面

## Why

change 0280 的 `permission.auto_approve_coeffects` 只能按 **coeffect** 收窄放行面，而
`tools.code_run` 的 coeffect 固定为 `process:spawn` + `filesystem:write`：无人值守部署只有
「允许执行任意命令」或「禁止执行任何命令」两种选择，无法表达「只允许 `git status` /
`pytest` 这类命令」。命令级收窄是无人值守落地的直接缺口。

## What Changes

- 新配置 `permission.auto_approve_commands`（三面 + 缺省 `""` = 不限制）。条目形态
  `tools.code_run:<命令前缀>`，逗号（含全角）分隔；条目在**校验期**逐项检查（工具 id 白名单、
  非空前缀、前缀不含 shell 元字符），非法即阻断启动。
- `PermissionGuard` 在 `AUTO_APPROVE` 档、配置非空时对 `tools.code_run` 的 `script` 做
  **保守匹配**：命令含 shell 元字符（`;|&$`<>()`、换行）⇒ 一律拒绝；否则做**词元边界前缀**
  匹配（完全相等，或前缀后接空白）。不匹配 ⇒ `deny`（不进审批、不执行）。错误信息不回显
  命令正文。
- 配置为空 / 非 auto-approve 档 / 其他工具 ⇒ 行为逐字不变。命令允许面**不是沙箱**（不做
  命令解析、不支持通配/正则、不隔离进程），文档与规格如实标注。

## Impact

- 规格：`configuration` **ADDED**「自动放行的命令允许面配置」；`permission` **ADDED**
  「自动放行的命令允许面」。
- 代码：`src/core/configuration/manager.py`（ConfigSpec / 校验 / 访问器）、
  `src/core/permission/guard.py`（判定）、`src/core/runtime.py`（组合根接线）。
- 测试：新增 `tests/test_command_allowlist.py`。
- 文档：`02-modules/permission.md`、`03-interfaces/{permission,configuration}-interface.md`。

## 不做

- 不做 shell 解析 / AST / 白名单子命令（如 `git status` 之外的 `git push`）—— 前缀匹配是
  便利围栏，不是安全边界。
- 不支持通配符 / 正则 / 参数级约束。
- 不覆盖 `tools.code_run` 以外的工具（当前无其他执行命令的工具；未来新增须改规格）。
- 不改变非 auto-approve 档的审批语义，不替代 coeffect 允许面 / guardrail。
