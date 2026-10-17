# Delta — change 0230（orchestration：文件型检查点）

## ADDED Requirements

### Requirement: 文件型检查点实现

系统 SHALL 提供满足既有 `CheckpointFn` 协议的**文件型检查点**实现（`FileCheckpoint`）：
每次调用 SHALL 将 `task_id` / `session_id` / `plan`（`plan_to_dict` 形态）/ 已完成子任务 id
与结果写入**单个 JSON 文件**；写入 SHALL 原子（同目录临时文件 + `os.replace`），SHALL NOT
留下半写文件。路径 SHALL 可配置，缺省 `.core/scheduler-checkpoint.json`。实现 SHALL 可被上层
注入的检查点回调**覆盖**（`TaskScheduler(checkpoint=...)` 语义不变）；未显式传入
`FileCheckpoint` 时调度器 SHALL NOT 自行落盘（缺省行为逐字不变）。检查点内容 SHALL NOT 含
密钥（沿用记忆写入前的脱敏约束）。

#### Scenario: 文件型检查点原子落盘
- **GIVEN** 调度器注入了 `FileCheckpoint` 且一个波次收拢
- **WHEN** 检查点回调触发
- **THEN** 单个 JSON 文件包含任务标识、会话标识、计划与已完成结果，文件可被完整解析

#### Scenario: 文件型检查点可恢复
- **GIVEN** 已落盘的检查点文件
- **WHEN** 读取并重建计划
- **THEN** 计划字段（含成功标准 / 重新拆解计数）与已完成子任务结果可还原

#### Scenario: 上层注入覆盖文件型实现
- **GIVEN** 调用方显式传入其他检查点回调
- **WHEN** 调度器触发检查点
- **THEN** 只调用注入回调，`FileCheckpoint` 不参与（不产生文件 I/O）
