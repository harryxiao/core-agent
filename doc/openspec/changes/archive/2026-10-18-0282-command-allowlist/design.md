# 0282 — 设计

## D1 在 `PermissionGuard.confirm` 判定，不在 mode gate

`PermissionModeGate.authorize(op, target, coeffect)` 拿不到工具实参，无法看到命令正文。
`PermissionGuard.confirm(tool_id, args, coeffects, reversible)` 是唯一同时具备**模式**与
**实参**的接缝 ⇒ 判定放在 `confirm`，在 `authorize` 放行之后、guardrail 之前：
coeffect 允许面与模式语义保持原样，命令面再收一层；两层都通过才 `auto`。

## D2 条目形态与作用域

`tools.code_run:<命令前缀>`。工具部分**只接受** `tools.code_run`（当前唯一执行任意命令的
工具；其他工具没有「命令正文」语义）。前缀按原样保存（去首尾空白），不做大小写归一（命令
大小写敏感）。同一工具多个前缀保序去重。

工具**没有**条目 ⇒ 命令允许面不作用于它（例如 `file_write` 仍只看 coeffect 允许面）。
配置整体为空 ⇒ 关闭，与引入前逐字一致。

## D3 命令正文与匹配规则

- 正文取 `args["script"]`（`tools.code_run` schema 的必填参数）。
- 非字符串 / 缺失 ⇒ **fail-closed 拒绝**（配置了命令面却拿不到命令，不能默认放行）。
- **保守元字符拒绝**：`;` `|` `&` `$` 反引号 `<` `>` `(` `)` 与换行 / 回车，出现在命令
  **任意位置**即拒绝。
  理由：前缀匹配对 `git status; rm -rf /`、`git status && curl …`、`$(…)`、重定向一律无效；
  与其逐条模拟 shell 语法，不如整类拒绝。
- **词元边界前缀**：命令去首尾空白后等于某前缀，或以 `<前缀><空白>` 开头（`str.startswith(prefix + " ")`
  / `"\t"`）。`git statusx` 不匹配 `git status`。
- 前缀自身在校验期已拒绝元字符；运行期不再重复校验配置（配置不可变）。

## D4 错误信息不回显命令

命令正文可能含令牌（如 `curl -H "Authorization: Bearer …"`）⇒ 拒绝信息只报工具 id 与
「命令不在允许的前缀内」，不拼接 `script`。配置校验错误同样**不回显条目取值**，只报形态
要求与键名。

## D5 只作用于 auto-approve

非 auto-approve 档的命令执行仍走既有风险分级 / 审批语义；即使配置了命令面也不改变结果
（与 coeffect 允许面同口径）。命令面**不**放宽 coeffect 面：两者同时配置时取交集。

## D6 组合根接线

`build_runtime` 构造 `PermissionGuard` 时传
`allowed_commands=config.permission_auto_approve_commands()`；访问器返回
`dict[str, tuple[str, ...]]`（空 dict = 关闭）。未传参的既有构造（测试 / 嵌入式）行为不变。

## 反证（3/3）

1. 摘掉 `_command_allowed` 的元字符判定（恒 `True`）⇒ 分号注入用例红。
2. 把词元边界改为裸 `str.startswith(prefix)` ⇒ `git statusx` 误匹配用例红。
3. 摘掉 `confirm` 中的命令面分支 ⇒ 不匹配拒绝用例红。
   复原以 `md5sum` 校验一致。

## 局限

前缀匹配不是沙箱：命令参数可携带任意语义（`git config` 改配置、`pytest` 执行仓库代码）；
`cwd` 不受限；后台执行（`background=true`）同样只按正文匹配、不影响已启动进程。命令面只
降低「模型随手执行任意命令」的概率，不提供隔离。Python `type` 脚本通常含括号 / 分号，在
命令面开启时会被元字符规则拒绝 —— 这是保守取舍，不是缺陷。
