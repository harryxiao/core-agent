# Permission Specification Delta

## MODIFIED Requirements

### Requirement: 分级权限体系
系统 SHALL 将操作划分为只读查询（read）、数据编辑（data-edit）、高危操作（high-risk）三个等级，并对高危操作默认拦截。分级判定 SHALL 依据**语义分词**（工具 / 动作词的完整词元）而非对标识串的**任意子串**匹配 —— 命名空间前缀或无关子串的偶然命中 SHALL NOT 影响等级。对显式声明的**委托类 coeffect**（字面量 `agent:delegate`）SHALL 判为 read；该豁免 SHALL NOT 放宽为 `agent:` 前缀（其余 `agent:*` coeffect SHALL 仍按高危及后续规则处理）。

#### Scenario: 只读操作放行
- **GIVEN** 一个操作被判定为 `read` 等级
- **WHEN** 执行前经过权限引擎判定
- **THEN** 操作在 coeffect 约束满足时放行

#### Scenario: 高危操作默认拦截
- **GIVEN** 一个操作被判定为 `high-risk` 等级
- **WHEN** 未持有已批准的人工审批单
- **THEN** 操作被拦截，返回 `APPROVAL_REQUIRED`

#### Scenario: 无法归类的操作
- **GIVEN** 一个操作的等级无法归类
- **WHEN** 执行前经过权限引擎判定
- **THEN** 默认按 `high-risk` 处理（deny-by-default）

#### Scenario: 只读判定不因命名空间子串误判
- **GIVEN** 一个操作标识本身不含任何只读动作词，仅其**命名空间前缀**偶然含只读词子串（如 `tools.` 含 `"ls"`）
- **WHEN** 执行前经过权限引擎判定
- **THEN** SHALL NOT 判为 `read`（按 `high-risk` deny-by-default）

#### Scenario: 委托类 coeffect 判只读
- **GIVEN** 一个动作声明字面量 coeffect `agent:delegate`
- **WHEN** 执行前经过权限引擎判定
- **THEN** 判为 `read`

#### Scenario: 非委托 agent coeffect 不放宽
- **GIVEN** 一个动作声明 `agent:other`（非 `agent:delegate`）
- **WHEN** 执行前经过权限引擎判定
- **THEN** SHALL NOT 因该 coeffect 判为 `read`（豁免仅限字面量，不放宽为前缀）

### Requirement: 权限模式
系统 SHALL 提供启动级权限模式开关，支持 read-only / interactive / auto-approve / high-risk-block 四档，映射 config.permission.mode，CLI 以 `--permission-mode` 指定。

**auto-approve 为无人值守全放行档**：权限判定 SHALL 对一切可由权限层决定的操作放行 —— 含高危操作、不可逆写、出站网络与无法归类的动作 —— SHALL NOT 触发人工审批、SHALL NOT 因「不可逆」或「高风险」而阻断。auto-approve 与 interactive SHALL 在判定结果上有可见差异（interactive 高危走审批；auto-approve 直接放行）。

auto-approve 的全放行 SHALL 仅覆盖**权限层**的判定，SHALL NOT 越过与权限档正交的安全机制（如注入的 guardrail 拦截）；read-only 与 high-risk-block 两档的拒绝语义 SHALL 保持不变。

#### Scenario: read-only 拒绝写操作
- **GIVEN** 权限模式为 read-only
- **WHEN** 执行写 / 编辑 / 删除类操作
- **THEN** 操作被拒绝并返回 `PERMISSION_DENIED`

#### Scenario: interactive 高危走审批
- **GIVEN** 权限模式为 interactive
- **WHEN** 执行高危操作
- **THEN** 进入人工审批流，批准才放行

#### Scenario: auto-approve 全放行
- **GIVEN** 权限模式为 auto-approve，且无可用审批通道
- **WHEN** 执行高危 / 不可逆写 / 出站网络 / 无法归类动作
- **THEN** 操作被放行（仍记录可逆效应），SHALL NOT 返回 `APPROVAL_REQUIRED`，SHALL NOT 返回 `PERMISSION_DENIED`

#### Scenario: auto-approve 与安全红线正交
- **GIVEN** 权限模式为 auto-approve 且注入了独立安全机制（guardrail）
- **WHEN** 该机制判定拦截
- **THEN** 操作仍被拒绝（权限档全放行 SHALL NOT 越过正交红线）

#### Scenario: high-risk-block 阻断高危
- **GIVEN** 权限模式为 high-risk-block
- **WHEN** 执行高危操作
- **THEN** 无条件阻断，不进入审批流，返回拒绝
