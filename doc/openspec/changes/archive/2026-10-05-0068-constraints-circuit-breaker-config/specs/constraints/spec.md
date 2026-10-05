# constraints spec delta — constraints-circuit-breaker-config

**把熔断的阈值与冷却从「类默认写死」变成「可经配置覆盖」。** 构造面本就可注入
（`constraints-interface.md:62`），但唯一调用点 `runtime.py:431` 未传参 ⇒ 生产固定 5 次 / 30 秒，
配置面（yaml / env / CLI）无对应键（账本 E15）。

## MODIFIED Requirements

### Requirement: 容错中间件
系统 SHALL 提供熔断、降级、重试、回滚中间件，防止级联失败，失败时撤销本轮副作用。
熔断 SHALL **按工具（`tool_id`）隔离**：单个工具连续 N 次**执行失败**（超时/执行异常）
即打开该工具的熔断，后续调用**快速失败、不真正执行**该工具；冷却期后半开试探，
试探成功即闭合。**策略性拒绝**（输入校验失败 / coeffect 缺失 / 确认门拒绝）**不计入失败计数**、
也不影响其他工具。
熔断的**失败阈值 N** 与**冷却期** SHALL **可经配置覆盖**：键为 `constraints.failure_threshold`
（缺省 5）与 `constraints.cooldown_s`（缺省 30 秒），经 `ConfigSpec` **单一真源**解析
（优先级 CLI flag > env > config.yaml > 缺省），并据此装配组合根注入 loop 的熔断链。
取值 SHALL 受约束：阈值须为 **≥1 的整数**、冷却须为 **≥0 的数值**；**非法取值 SHALL 在校验期
被拒绝并阻断启动**（不得静默兜底为缺省值）。

#### Scenario: 熔断器打开
- **GIVEN** 某插件连续 N 次失败
- **WHEN** 下一次调用到达
- **THEN** 熔断器打开快速失败，冷却后半开试探

#### Scenario: 失败回滚
- **GIVEN** 一个子任务执行失败
- **WHEN** 重试与降级均不成功
- **THEN** 回滚中间件撤销本轮副作用，任务不整体崩溃

#### Scenario: 熔断按工具隔离
- **GIVEN** 工具 A 连续执行失败达到阈值、工具 B 健康
- **WHEN** 下一次分别调用 A 与 B
- **THEN** A 快速失败（熔断打开），B 正常执行；A 的熔断不影响 B

#### Scenario: 策略拒绝不计入熔断
- **GIVEN** 某工具被反复以不合法参数调用（输入校验失败）或确认门拒绝，次数远超阈值
- **WHEN** 后续调用到达
- **THEN** 该工具熔断器仍为闭合（策略性拒绝不计入失败计数），被合法调用时仍正常执行

#### Scenario: 冷却后半开试探成功即闭合
- **GIVEN** 某工具熔断已打开且冷却期已过
- **WHEN** 下一次调用执行成功
- **THEN** 该工具熔断器闭合，后续调用正常执行

#### Scenario: 熔断阈值与冷却可经配置覆盖
- **GIVEN** 配置将 `constraints.failure_threshold` 设为 2、`constraints.cooldown_s` 设为 10
- **WHEN** 系统启动装配
- **THEN** 组合根注入 loop 的熔断链以 2 次失败 / 10 秒冷却为准（覆盖类默认 5 / 30）
- **AND** 同一取值经 CLI flag / env / config.yaml 任一面设置均生效，优先级链一致

#### Scenario: 非法熔断取值校验期拒绝
- **GIVEN** 配置将 `constraints.failure_threshold` 设为 0 或非数值、或 `constraints.cooldown_s` 设为负数
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值范围（不静默回落为缺省值）
