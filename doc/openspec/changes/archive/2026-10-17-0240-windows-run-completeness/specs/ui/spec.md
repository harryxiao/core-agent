## MODIFIED Requirements

### Requirement: code_run 活动标题按方言命名

系统 SHALL 在 TUI（或等价活动流）呈现 tools.code_run 时，按本次调用的有效 type 选用
友好名，避免一律标成 Bash 误导操作者与后续模型回灌。

- powershell => 友好名 SHALL 含 PowerShell（或同义固定词，实现钉死一处）；
- bash => 友好名 SHALL 含 Bash；
- python => 友好名 SHALL 含 Python；
- **未指定 type**：友好名 SHALL 按注入的**有效平台缺省**命名（powershell → PowerShell，
  bash → Bash）；平台事实不可得时 SHALL 用中性 `Shell`，SHALL NOT 谎报 Bash；
- 括号内脚本摘要口径（首行有界）SHALL 与既有活动块摘要规则一致。

#### Scenario: PowerShell 调用不以 Bash 为标题

- **GIVEN** 一次 tools.code_run 动作的有效 type 为 powershell
- **WHEN** 渲染活动标题
- **THEN** 标题友好名表明 PowerShell，SHALL NOT 仅显示为 Bash

#### Scenario: bash 调用仍显示 Bash

- **GIVEN** 一次 tools.code_run 动作的有效 type 为 bash
- **WHEN** 渲染活动标题
- **THEN** 标题友好名表明 Bash

#### Scenario: 未指定 type 时按有效缺省命名

- **GIVEN** 一次 tools.code_run 动作未指定 type
- **WHEN** 注入的平台缺省为 powershell 或 bash
- **THEN** 标题分别显示 PowerShell 或 Bash；平台事实不可得时显示中性 `Shell`，
  SHALL NOT 显示为 Bash
