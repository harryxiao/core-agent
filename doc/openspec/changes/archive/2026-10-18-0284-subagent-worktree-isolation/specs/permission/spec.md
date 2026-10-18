## ADDED Requirements

### Requirement: 工作树工具权限口径

系统 SHALL 按既有词元分级规则为工作树工具定级，SHALL NOT 为多动作工具引入按 action
变化的风险等级：

- `tools.worktree.list` SHALL 判 `READ`（操作 id 含只读词元 `list`），coeffect SHALL 为
  `worktree:read`；read-only / interactive / auto-approve / high-risk-block 四档 SHALL 均放行。
- `tools.worktree.discard` SHALL 判 `HIGH_RISK`（操作 id 无可归类词元，走 deny-by-default），
  coeffect SHALL 为 `worktree:write`，且 SHALL 声明为不可逆；interactive 档 SHALL 要求人工
  审批，read-only 与 high-risk-block 档 SHALL 拒绝，auto-approve 档 SHALL 放行但 SHALL 仍受
  `permission.auto_approve_coeffects` 允许面约束（未包含 `worktree:write` 时 SHALL NOT 自动放行）。

两个工具 SHALL 只挂主工具面，SHALL NOT 出现在子 Agent 工具面，也 SHALL NOT 进入 MCP 默认
暴露集（`worktree:read` 不属于默认暴露的只读 coeffect）。

#### Scenario: 只读清单放行

- **GIVEN** 任意权限档
- **WHEN** 调用 `tools.worktree.list`
- **THEN** 风险等级 SHALL 为 READ 且 SHALL NOT 触发审批

#### Scenario: 丢弃需审批

- **GIVEN** interactive 权限档
- **WHEN** 调用 `tools.worktree.discard`
- **THEN** 风险等级 SHALL 为 HIGH_RISK，SHALL 进入人工审批流

#### Scenario: 只读与高危阻断档拒绝丢弃

- **GIVEN** read-only 或 high-risk-block 权限档
- **WHEN** 调用 `tools.worktree.discard`
- **THEN** SHALL 返回拒绝，SHALL NOT 执行删除

#### Scenario: auto-approve 受 coeffect 允许面约束

- **GIVEN** auto-approve 档且 `permission.auto_approve_coeffects` 未包含 `worktree:write`
- **WHEN** 调用 `tools.worktree.discard`
- **THEN** SHALL NOT 自动放行（仍走审批或拒绝，取决于允许面语义）
