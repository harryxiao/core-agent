Evolution 并发评测资源上限：多候选并发留出评测超配额时排队或限流，资源总量受配额约束，防止评测资源耗尽失真。（来源：架构查漏补缺探索结论，2026-09-22）

## MODIFIED Requirements

### Requirement: 留出评测
系统 SHALL 在留出集上评测候选，防止过拟合与退化。

#### Scenario: 留出集通过则发布
- **GIVEN** 候选通过验证门
- **WHEN** Evaluator 留出集评测不退化
- **THEN** verdict=publish，结晶入库

#### Scenario: 留出集退化回滚
- **GIVEN** 候选在留出集上退化
- **WHEN** Evaluator 判定退化
- **THEN** verdict=rollback，自动回滚并冻结冷却期

#### Scenario: 并发评测资源上限
- **GIVEN** 多个候选同时进入留出评测
- **WHEN** 并发评测请求超过资源配额上限
- **THEN** 超限请求排队或限流，评测资源总量受配额约束，不因并发耗尽资源导致评测结果失真
