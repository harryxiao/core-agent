# Orchestration Specification Delta

## MODIFIED Requirements

### Requirement: 子任务验收门
系统 SHALL 对带验收标准的子任务结果经 LLM 对照判定（验收门）：判定通过才记录完成并推进；判定不通过或判定器不可用时标记失败不推进（fail-closed）；无验收标准时退化为离线非空判定，不调用模型。子任务**执行单元**返回**失败态**（循环未达成目标 / 异常终止 / 预算耗尽）时，验收门 SHALL 判**不通过**（fail-closed），SHALL NOT 因合成回复非空而通过；该失败态 SHALL 传播至子任务终态（`ok = 验收通过 且 执行未失败`）与 fan-in 推进判据。

#### Scenario: 验收门 LLM 判定
- **GIVEN** 子任务带验收标准且执行完成
- **WHEN** 验收门对照 acceptance 判定结果
- **THEN** 判定通过才记录完成并推进下一波次，判定结论与理由写入 trace

#### Scenario: 验收判定失败不推进
- **GIVEN** 子任务结果未达验收标准（或判定调用失败）
- **WHEN** 验收门判定不通过
- **THEN** 子任务标记失败（含理由），不静默推进，任务转入 RECOVERING

#### Scenario: 无验收标准离线判定
- **GIVEN** 子任务未定义验收标准
- **WHEN** 验收门校验结果
- **THEN** 退化为离线判定（结果非空即通过），不调用模型

#### Scenario: 执行失败态不因非空合成回复通过
- **GIVEN** 子任务执行单元返回失败态（`failed=True`）却产出非空回复
- **WHEN** 验收门校验结果
- **THEN** 该子任务标记失败（含理由），不记录完成、不推进后继波次，任务转入 RECOVERING
