评测基建增量规格，将验证门与留出评测从"概念层"工程化为可落地的评测基建（基准集 + 评测运行器 + 指标对比基线），对齐 OpenAI Agents eval / LangSmith eval。

## ADDED Requirements

### Requirement: 评测基建
系统 SHALL 提供可落地的评测基建（基准集 + 评测运行器 + 指标对比基线），支撑验证门与留出评测的工程化执行。

#### Scenario: 基准集注册
- **GIVEN** 一个评测基准（含输入样例与期望指标）准备就绪
- **WHEN** 进化引擎或运维注册该基准
- **THEN** 基准入库并可被留出评测按需引用

#### Scenario: 候选批量评测
- **GIVEN** 一个候选通过验证门
- **WHEN** Evaluator 运行评测
- **THEN** 评测运行器在留出集上批量执行，产出候选指标报告

#### Scenario: 与基线对比判定退化
- **GIVEN** 候选评测指标与当前基线指标均已采集
- **WHEN** Evaluator 对比二者
- **THEN** 不退化则 publish，退化则 rollback，指标差异归档供诊断归因
