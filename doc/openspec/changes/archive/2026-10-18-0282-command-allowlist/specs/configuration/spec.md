## ADDED Requirements

### Requirement: 自动放行的命令允许面配置

系统 SHALL 将 `permission.auto_approve_commands` 纳入 ConfigSpec 单一真源，三面（CLI flag
`--permission.auto-approve-commands` / env `CORE_PERMISSION_AUTO_APPROVE_COMMANDS` /
config.yaml）一一对应并参与优先级链（CLI > env > config.yaml > 默认值）。默认值 SHALL 为
空串，表示不限制（行为与引入前一致）。

取值 SHALL 为逗号（含全角 `，`）分隔的条目列表；条目形态为 `tools.code_run:<命令前缀>`：
工具部分 SHALL 为 `tools.code_run`（当前唯一执行任意命令的工具），前缀 SHALL 非空（去首尾
空白后）且 SHALL NOT 含 shell 元字符（`;` `|` `&` `$` 反引号 `<` `>` `(` `)`、换行 /
回车）。空条目 SHALL 被忽略；重复条目 SHALL 去重并保序。任一非法条目 SHALL 在校验期判为
错误并**阻断启动**，错误信息 SHALL 指明键名与合法形态，SHALL NOT 回显条目取值。

访问器 `permission_auto_approve_commands()` SHALL 返回 `{工具 id: (前缀, ...)}`；配置未加载
或未配置时 SHALL 返回空映射。

#### Scenario: 缺省不限制

- **GIVEN** 配置未声明 `permission.auto_approve_commands`
- **WHEN** 读取 `permission_auto_approve_commands()`
- **THEN** SHALL 返回空映射，auto-approve 档的命令执行 SHALL 与引入前逐字一致

#### Scenario: 三面取值与优先级

- **GIVEN** yaml / env / CLI 同时配置不同的命令允许面
- **WHEN** 加载配置
- **THEN** 访问器 SHALL 返回 CLI 的取值

#### Scenario: 非法条目阻断启动

- **GIVEN** 任一条目缺少 `:`、工具 id 不是 `tools.code_run`、前缀为空、或前缀含 shell 元字符
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明键名与合法形态
- **AND THEN** 错误信息 SHALL NOT 包含该条目或前缀的取值

#### Scenario: 全角逗号与去重

- **GIVEN** 取值为 `tools.code_run:git status，tools.code_run:pytest, tools.code_run:git status`
- **WHEN** 加载配置
- **THEN** 访问器 SHALL 返回 `{"tools.code_run": ("git status", "pytest")}`（去重、保序）
