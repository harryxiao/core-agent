# Constraints Specification

## Purpose
约束与中间件在模型执行前后插入标准化校验逻辑，把自由文本输出转化为结构化、可验证、可容错的执行指令，系统性降低输出错误率，并防止单点失败级联。

## Requirements

### Requirement: 输入输出校验
系统 SHALL 在工具调用前校验输入 schema/coeffect，在调用后把自由文本解析为结构化指令，解析失败绝不带病执行。

- **口径单一真源**：调用前的 schema 校验（必填 / 类型）SHALL 只有一份实现，即
  :class:`Validator`（`validate_input`）。**工具层（`ToolProvider`）SHALL 委托该口径**，
  SHALL NOT 另实现校验副本；同一非法调用经工具层与经校验中间件得到的拒绝口径 SHALL 一致
  （同样的结构化错误信息）。

#### Scenario: 输入校验失败拒绝执行
- **GIVEN** 一个工具调用的参数不满足 schema
- **WHEN** 校验中间件处理该调用
- **THEN** 调用被拒绝并返回结构化错误

#### Scenario: 输出解析失败不执行
- **GIVEN** 模型返回无法解析的自由文本
- **WHEN** 解析中间件处理该输出
- **THEN** 不执行，重试（有限次）或请求模型修正

#### Scenario: 工具层与校验中间件口径一致
- **GIVEN** 一个参数不满足 schema 的工具调用（缺参或错型）
- **WHEN** 分别经工具层的调用前校验与校验中间件的 `validate_input` 判定
- **THEN** 两者以**同一口径**拒绝（同样的结构化错误信息），不存在两套判定
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

**重试中间件** SHALL 接入工具调用链（经 loop 侧适配层 `FaultChain` 包裹执行接缝）：仅当工具调用
**执行类失败**且失败码 ∈ **显式白名单** `{TIMEOUT, EXECUTION_FAILED}`（未来新增错误码 **fail-closed
不重试**）、且该工具**可逆**（`reversible=True`）时，才按**退避策略**重试；重试次数上界经
`constraints.retry_attempts`（**≥0 的整数**，**0 = 关闭 = 缺省**）配置，经 `ConfigSpec` 单一真源解析，
**非法取值 SHALL 在校验期被拒绝并阻断启动**。**策略性拒绝**（输入校验 / coeffect 缺失 / 确认门拒绝 /
熔断打开）SHALL **不重试**；**不可逆工具** SHALL **不重试**（避免部分外写被重试放大）。重试**耗尽**
时 SHALL **原样返回最后一次失败结果**（不降级、不改写失败码）—— 失败态照常透出供上层回滚与
ReAct 自愈。`retry_attempts` 取 `0`（缺省）时 SHALL NOT 重试，既有路径**逐字不变**。

**库能力边界**：`Fallback`（降级）与 `Pipeline`（洋葱管道）为**保留库能力**（接口齐备、有单元测试
覆盖），**不接入**生产工具链 —— 降级回复会终结 loop 并静默抑制失败态回滚，与 `act` 的结果语义
（失败致 trace 回滚、工具失败不判轮失败）相冲；`Rollback` 亦**不重复接入**（失败回滚已由 loop 级
`rollback(trace_id)` 单一路径满足）。

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
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值范围（不静默兜底为缺省值）

#### Scenario: 可逆工具执行超时后重试成功
- **GIVEN** 一个可逆工具的首次调用以 `TIMEOUT` 失败、第二次调用成功，且 `retry_attempts ≥ 1`
- **WHEN** 该工具被调用
- **THEN** 适配层按退避策略重试，最终返回成功结果，且只记录一次可逆效应

#### Scenario: 不可逆工具不重试
- **GIVEN** 一个不可逆工具的调用以 `TIMEOUT` 失败，且 `retry_attempts ≥ 1`
- **WHEN** 该工具被调用
- **THEN** 适配层**不重试**，首次失败结果原样透出（失败致本轮 trace 回滚）

#### Scenario: 策略拒绝不重试
- **GIVEN** 一次调用以策略性拒绝（如 `INVALID_ARGS`）失败
- **WHEN** 结果判定是否重试
- **THEN** **不重试**（策略性拒绝不在可重试白名单内，重试不能改变判定）

#### Scenario: 重试耗尽原样返回不降级
- **GIVEN** 一个可逆工具连续以 `EXECUTION_FAILED` 失败、重试次数已达 `retry_attempts` 上界
- **WHEN** 重试耗尽
- **THEN** **原样返回**最后一次失败结果（`failed=True` 且失败码不变），**不降级**为备用回复

#### Scenario: retry_attempts 缺省零时逐字不变
- **GIVEN** `constraints.retry_attempts` 未配置（缺省 0）
- **WHEN** 一次可逆工具调用以 `TIMEOUT` 失败
- **THEN** 适配层**不包裹**执行接缝，调用路径与改动前**逐字不变**（无重试）
### Requirement: 上下文压缩中间件
系统 SHALL 自动清理对话历史中的无效信息，对抗信息腐烂。

#### Scenario: 清理冗余上下文
- **GIVEN** 历史中包含已完成子任务与重复内容
- **WHEN** 上下文压缩中间件运行
- **THEN** 无效信息被清理，关键约束与未决事项保留
