## ADDED Requirements

### Requirement: 运行中取消与消费方断流

系统 SHALL 让运行中任务的取消**打断在途执行**：`cancel(task_id)` SHALL 置取消信号并取消当前
波次的扇出执行单元，SHALL NOT 等待在途子任务自然完成；执行流 SHALL 以 `task_failed`
（错误码 `TASK_CANCELLED`）终止，任务状态 SHALL 进入 `FAILED`，进度上下文 SHALL 释放，
已持久化的断点上下文沿用既有策略保留。对已处于终态（`DONE` / `FAILED`）的任务重复取消
SHALL 幂等（不抛 `INVALID_TRANSITION`）。

消费方在任务流未达终态前断开（停止消费 / 关闭事件流 / 取消消费任务）时，调度器 SHALL
取消在途扇出执行单元并释放任务级上下文，SHALL NOT 遗留后台子任务继续执行；未达终态的任务
SHALL 转入 `FAILED`，SHALL NOT 伪装为成功。

任务到达任一终态后，调度器 SHALL 释放任务级结果缓存与取消信号登记。

#### Scenario: 取消打断在途子任务
- **GIVEN** 任务运行中，一个子任务仍在执行且尚未返回
- **WHEN** 调用 `cancel(task_id)`
- **THEN** 在途子任务被取消，执行流以 `task_failed`（`TASK_CANCELLED`）终止，任务状态为
  `FAILED`，且不等待该子任务自然完成

#### Scenario: 消费方断流释放执行单元
- **GIVEN** 任务流已发出部分事件且子任务仍在执行
- **WHEN** 消费方关闭事件流（不再消费）
- **THEN** 在途子任务被取消，任务转入 `FAILED`，任务级结果缓存被清空，无后台任务继续执行

#### Scenario: 终态清理任务级缓存
- **GIVEN** 任务已到达 `DONE` 或 `FAILED`
- **WHEN** 执行流结束
- **THEN** 任务级结果缓存与取消信号登记被释放

#### Scenario: 重复取消终态任务幂等
- **GIVEN** 任务已处于 `FAILED`（或 `DONE`）
- **WHEN** 再次调用 `cancel(task_id)`
- **THEN** 不抛 `INVALID_TRANSITION`，任务保持原终态
