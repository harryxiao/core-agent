# Delta — change 0248（orchestration R6）

## MODIFIED Requirements

### Requirement: 目标监控
系统 SHALL 用 Goal 与 SuccessCriteria 定义任务级成功标准，并由 ProgressTracker 追踪每子任务
进度与整体目标推进，进度未达标时触发重试或重规划。

成功标准 SHALL 默认由拆解器在拆解时生成（顶层 `success_criteria`，2-5 条、每条可客观判定
真伪、覆盖整体目标而不复述子任务 acceptance）；调用方显式提供的非空标准 SHALL 优先于生成
标准；拆解失败回落的单子任务计划 SHALL NOT 自带标准（同源判定 fail-closed 不得把任务拖死）。
重新拆解时原标准非空 SHALL 保留。

任务终态 SHALL 由任务级判定器对照 Goal + SuccessCriteria + 子任务结果判定；未注入判定器而
存在标准时 SHALL 以 `MISSING_SUCCESS_CHECKER` 失败（fail-fast）；判定器异常或返回非法结果
SHALL fail-closed（判未达标），SHALL NOT 裸崩或静默放行。未达标 SHALL 进入恢复回路：重拆
预算未用尽则重新拆解，否则任务判 `FAILED`。

ProgressTracker SHALL 维护每子任务的三态进度：已开始（`started`）、已完成（`completed`）、
失败待恢复（`failed`）；重试开始与完成 SHALL 清除失败标记，重新拆解 SHALL 清空三态。

#### Scenario: 成功标准定义
- **GIVEN** 任务进入拆解且调用方未显式提供成功标准
- **WHEN** planner 产出拆解结果
- **THEN** 计划的 success_criteria 取自 planner 生成的标准（去空白、去重、至多 5 条），
  标准可判定真伪、可度量（SMART）

#### Scenario: 显式标准优先与回落无标准
- **GIVEN** 调用方显式提供了非空成功标准，或 planner 调用失败回落为单子任务
- **WHEN** 拆解完成
- **THEN** 显式标准 SHALL 覆盖生成标准；回落的单子任务计划不带生成标准

#### Scenario: 进度追踪
- **GIVEN** 任务执行中
- **WHEN** 子任务开始、失败、重试
- **THEN** ProgressTracker 的 started / completed / failed 计数随之更新并反映整体目标推进

#### Scenario: 任务级判定
- **GIVEN** 全部子任务通过验收且计划带有成功标准
- **WHEN** 任务进入 VERIFYING
- **THEN** 判定器接收 Goal、成功标准与子任务结果，判定通过才判 `DONE`

#### Scenario: 未达标重试/重规划
- **GIVEN** 子任务进度未达标或任务级判定未通过
- **WHEN** 进度监控检测到偏差
- **THEN** 触发重新拆解（预算未用尽）或判 `FAILED`，衔接状态机 RECOVERING

#### Scenario: 判定器异常 fail-closed
- **GIVEN** 任务级判定器抛出异常或返回非法结果
- **WHEN** 任务进入 VERIFYING
- **THEN** 判定按未达标处理并进入恢复回路，任务不裸崩、不静默判 `DONE`
