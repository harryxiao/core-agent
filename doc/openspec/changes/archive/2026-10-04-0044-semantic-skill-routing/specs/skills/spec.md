# Skills Specification Delta

## ADDED Requirements

### Requirement: 语义路由（semantic routing）
系统 SHALL 在**词法匹配全无命中**时提供语义路由兜底：以注入的语义打分器（缺省不启用）对候选技能
逐条打分，达阈值者按分排序返回；语义命中 SHALL 视为命中（不记未命中）。

- **触发**：仅当词法匹配无任何命中（即原本记 miss 的那条路径）才启用语义；词法命中时 SHALL NOT
  产生模型调用。
- **打分口径**：打分器契约 `(任务文本, 候选技能列表) -> {skill_id: 分值}`；候选 SHALL 只含
  `active`/`gray` 技能。语义分值 SHALL 不低于阈值（缺省 0.5）才被采纳。
- **归组/排序**：命中项按分值降序，返回 Top-K（与词法路径同签名）。
- **降级**：未注入打分器 / 打分器不可用 / 分值低于阈值 → 行为 SHALL 与纯词法一致（返回词法结果，
  无命中则记 miss）；打分器故障 SHALL NOT 中断路由（`match` 不得向调用方抛异常）。

#### Scenario: 词法无命中时语义兜底命中
- **GIVEN** 技能库有 `task_types=["summarize report"]` 的技能，任务文本与任何技能词法不相交
- **WHEN** 注入的语义打分器给该技能打分 0.9（≥ 阈值）
- **THEN** `match` 返回该技能（`score=0.9`），且**不记 miss**

#### Scenario: 词法命中时不走语义
- **GIVEN** 任务文本词法命中某技能
- **WHEN** 调用 `match`
- **THEN** 返回词法结果，且语义打分器**不被调用**

#### Scenario: 未注入打分器时保持词法
- **GIVEN** 未注入语义打分器
- **WHEN** 词法无命中
- **THEN** 返回空列表并记 miss（与既有行为一致）

#### Scenario: 语义分值低于阈值不采纳
- **GIVEN** 词法无命中，语义打分器给全部候选打分均低于阈值
- **WHEN** 调用 `match`
- **THEN** 返回空列表并记 miss

#### Scenario: 打分器不可用时降级为词法
- **GIVEN** 词法无命中，语义打分器整体抛出异常
- **WHEN** 调用 `match`
- **THEN** 不抛出、返回空列表并记 miss（路由不得因打分器故障而中断）
