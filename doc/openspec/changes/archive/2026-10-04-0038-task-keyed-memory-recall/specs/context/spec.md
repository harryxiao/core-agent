# Context Engineering Specification Delta

## MODIFIED Requirements

### Requirement: 动态上下文构建
系统 SHALL 以**任务目标**为检索信号按需加载上下文（L2 事实检索以 task 为 query；stage 为装配阶段标注、暂不参与事实选择），控制注入 token 上界，超预算裁剪低相关度内容。

#### Scenario: 按需加载与预算控制
- **GIVEN** 一个任务处于某阶段
- **WHEN** 上下文装配器构建上下文
- **THEN** 以任务目标为检索信号加载相关事实，token 控制在预算内

#### Scenario: 按任务召回事实
- **GIVEN** MemoryStore 含与当前任务相关的历史事实
- **WHEN** 上下文装配器以该任务构建上下文
- **THEN** 命中与任务相关的事实并注入 `facts`（检索 query 为 task，非阶段名）

#### Scenario: 超预算裁剪保留关键
- **GIVEN** 装配结果 token 超预算
- **WHEN** 预算管理器裁剪
- **THEN** 裁剪低相关度内容，优先保留宪章/未决事项/验收标准
