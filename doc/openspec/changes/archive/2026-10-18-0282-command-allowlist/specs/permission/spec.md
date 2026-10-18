## ADDED Requirements

### Requirement: 自动放行的命令允许面

auto-approve 档 SHALL 支持以 `permission.auto_approve_commands` 为**指定工具**声明允许的
**命令前缀**（见 configuration「自动放行的命令允许面配置」；缺省空 = 不限制）。某工具存在
条目时，其命令执行 SHALL 先通过命令检查，判定 SHALL 在 coeffect 允许面放行之后完成；
两层均通过才 SHALL 判定 `auto`。

命令检查 SHALL 取值于工具实参 `script`，规则如下：`script` 非字符串或缺失 ⇒ SHALL 拒绝
（fail-closed）；`script` 含 shell 元字符（`;` `|` `&` `$` 反引号 `<` `>` `(` `)`、换行 /
回车）⇒ SHALL 拒绝；否则命令（去首尾空白）与某前缀**完全相等**或**以「前缀 + 空白」开头**
⇒ SHALL 放行，其余 SHALL 拒绝。

拒绝 SHALL 为 `PERMISSION_DENIED`（结构化拒绝）：SHALL NOT 进入审批流、SHALL NOT 执行
动作；错误信息 SHALL NOT 回显命令正文。无条目的工具 SHALL NOT 受本要求约束；配置为空时
auto-approve 的既有全放行语义 SHALL 逐字不变。非 auto-approve 档 SHALL 忽略命令允许面并
按该档既有语义处理。

命令允许面 SHALL NOT 被描述或实现为沙箱：它不解析命令语义、不支持通配 / 正则、不隔离
进程与环境，只降低「执行任意命令」的概率；SHALL NOT 取代 coeffect 允许面、guardrail 或
沙箱机制（同时配置时取交集）。

#### Scenario: 前缀匹配放行

- **GIVEN** auto-approve 且 `tools.code_run` 允许前缀 `git status`
- **WHEN** 执行 `script="git status"` 或 `script="git status --short"`
- **THEN** 判定 SHALL 放行（`auto`），不进入审批

#### Scenario: 不匹配拒绝

- **GIVEN** auto-approve 且 `tools.code_run` 允许前缀 `git status`
- **WHEN** 执行 `script="rm -rf /tmp/x"`
- **THEN** 判定 SHALL 以 `PERMISSION_DENIED` 拒绝，SHALL NOT 执行命令
- **AND THEN** 错误信息 SHALL NOT 包含 `rm -rf /tmp/x`

#### Scenario: 词元边界匹配

- **GIVEN** auto-approve 且 `tools.code_run` 允许前缀 `git status`
- **WHEN** 执行 `script="git statusx"`
- **THEN** 判定 SHALL 拒绝（不按裸前缀匹配）

#### Scenario: shell 元字符一律拒绝

- **GIVEN** auto-approve 且 `tools.code_run` 允许前缀 `git status`
- **WHEN** 执行 `script="git status; rm -rf /tmp/x"`（或以 `&&`、`$(...)`、重定向续接）
- **THEN** 判定 SHALL 拒绝，即使命令以允许前缀开头

#### Scenario: 命令取值缺失时 fail-closed

- **GIVEN** auto-approve 且 `tools.code_run` 配置了允许前缀
- **WHEN** 工具实参的 `script` 缺失或不是字符串
- **THEN** 判定 SHALL 拒绝，SHALL NOT 放行

#### Scenario: 无条目工具与空配置不受影响

- **GIVEN** auto-approve 且命令允许面为空（或某工具无条目）
- **WHEN** 执行任意命令（或调用该工具）
- **THEN** 判定 SHALL 放行，与引入前逐字一致

#### Scenario: 非 auto-approve 档忽略命令允许面

- **GIVEN** 权限档为 interactive 且配置了命令允许面
- **WHEN** 执行不匹配前缀的命令
- **THEN** 判定 SHALL 按 interactive 既有语义处理（不可逆写进入审批），命令面 SHALL NOT
  改变结果
