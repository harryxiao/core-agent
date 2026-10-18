## MODIFIED Requirements

### Requirement: 分级权限体系
系统 SHALL 将操作划分为只读查询（read）、数据编辑（data-edit）、高危操作（high-risk）三个等级，并对高危操作默认拦截。分级判定 SHALL 依据**语义分词**（工具 / 动作词的完整词元）而非对标识串的**任意子串**匹配 —— 命名空间前缀或无关子串的偶然命中 SHALL NOT 影响等级。对显式声明的**委托类 coeffect**（字面量 `agent:delegate`）SHALL 判为 read；该豁免 SHALL NOT 放宽为 `agent:` 前缀（其余 `agent:*` coeffect SHALL 仍按高危及后续规则处理）。

只读动作词集合 SHALL 包含 `process`（后台任务巡检）；`process` 词元判为 `read` SHALL NOT 豁免同标识中**更高优先**的高危词元 —— 含 `kill` 的标识 SHALL 仍判 `high-risk`。

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

#### Scenario: 任务巡检判只读
- **GIVEN** 动作标识含 `process` 词元（如 `tools.process`）且不含任何高危词元
- **WHEN** 执行前经过权限引擎判定
- **THEN** 判为 `read`，在 coeffect 约束满足时放行

#### Scenario: 终止进程仍判高危
- **GIVEN** 动作标识为 `tools.process_kill`（同时含 `process` 与 `kill` 词元）
- **WHEN** 执行前经过权限引擎判定
- **THEN** 判为 `high-risk`（高危词元优先），未获审批时返回 `APPROVAL_REQUIRED`
