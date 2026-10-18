## ADDED Requirements

### Requirement: 自动放行的 coeffect 允许面

auto-approve 档 SHALL 支持以 `permission.auto_approve_coeffects` 声明**允许的 coeffect 集合**
（缺省空 = 不限制，既有全放行语义不变）。配置非空时，权限门 SHALL 对动作声明的**全部**
coeffect 做子集检查：任一 coeffect 不在允许集合内 ⇒ SHALL 以 `PERMISSION_DENIED` 拒绝，
SHALL NOT 进入审批流，SHALL NOT 执行动作。判定 SHALL 在 auto-approve 的短路放行**之前**完成。

该允许面 SHALL 只作用于 auto-approve 档：read-only / interactive / high-risk-block 的判定与
审批语义 SHALL 保持不变（配置对它们无效果）。允许面 SHALL NOT 取代或放宽 coeffect 声明解析、
guardrail 等正交安全机制；未声明任何 coeffect 的动作不受本限制约束。

#### Scenario: 允许集合内的动作放行

- **GIVEN** auto-approve 且允许面为 `filesystem:write`
- **WHEN** 动作声明 coeffect `filesystem:write`
- **THEN** 判定 SHALL 放行（`auto`，不进入审批）

#### Scenario: 越界 coeffect 拒绝

- **GIVEN** auto-approve 且允许面为 `filesystem:write`
- **WHEN** 动作声明 coeffect `network:outbound`
- **THEN** 判定 SHALL 以 `PERMISSION_DENIED` 拒绝，SHALL NOT 执行动作

#### Scenario: 多 coeffect 全含语义

- **GIVEN** auto-approve 且允许面为 `filesystem:write`
- **WHEN** 动作声明 `filesystem:write` 与 `process:spawn`
- **THEN** 判定 SHALL 拒绝（任一越界即拒绝），错误信息 SHALL 列出未授权的 coeffect

#### Scenario: 允许面为空保持全放行

- **GIVEN** auto-approve 且允许面未配置或为空
- **WHEN** 动作声明任意 coeffect（含高危 / 出站网络）
- **THEN** 判定 SHALL 放行，与引入本允许面前逐字一致

#### Scenario: 非 auto-approve 档忽略允许面

- **GIVEN** 权限档为 interactive（或 read-only / high-risk-block）且配置了允许面
- **WHEN** 动作声明越界 coeffect
- **THEN** 判定 SHALL 按该档既有语义处理，允许面 SHALL NOT 改变结果
