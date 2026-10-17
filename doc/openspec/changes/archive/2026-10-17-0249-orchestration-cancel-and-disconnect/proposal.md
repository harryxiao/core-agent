# Proposal — 运行中取消与消费方断流（change 0249）

## 为什么

批次 D3 的已知局限（ADR-0234 / ADR-0235）：`TaskScheduler.cancel` 只做状态转移与
`tracker.reset`，**不断流** —— 已进入波次的子任务继续跑完，取消后仍可能写回结果；消费方
提前断开（停止消费 / 关闭事件流 / 取消消费任务）时，`_stream_wave` 创建的 fan-out 任务
无人取消，成为后台孤儿；`_results`（任务级结果缓存）只在重拆时清理，任务终态后仍驻留。

规格「断点续跑」R4 的取消 Scenario 要求「任务终止并释放已占用的执行单元与资源」，上述
三条均未闭合。

## 改什么

- `cancel(task_id)`：置**取消信号**并取消当前波次的 fan-out 执行单元；任务转 `FAILED`、
  释放进度上下文；终态任务重复取消**幂等**（不抛 `INVALID_TRANSITION`）。
- 执行流以 `task_failed`（新错误码 `TASK_CANCELLED`）终止，`run()` 按原错误码抛错。
- `_stream_wave`：注册在途 fan-out 任务；`finally` 取消并回收（任何退出路径都不留后台
  子任务）；协作取消（取消信号已置）的 `CancelledError` 安静收拢，外部取消照常透传。
- `astream` 增加薄包装：任意退出路径（正常终态 / 取消 / 消费方断流 / 异常）经 `finally`
  释放任务级上下文（`_results` / 取消信号 / 在途任务登记）；未达终态 ⇒ 转 `FAILED` 并
  trace `task_aborted`（消费方断流不得伪装成功）。

## 影响面

- `src/core/orchestration/{scheduler,errors}.py`
- 规格：`orchestration` 新增 Requirement「运行中取消与消费方断流」（4 Scenario）
- 文档：`03-interfaces/orchestration-interface.md`（错误码表 + 取消/断流语义）、
  `02-modules/orchestration.md`
- 测试：`tests/test_orchestration.py`（取消打断 / 断流回收 / 终态清理 / 重复取消幂等）

## 不做

- 不改 `suspend` / `resume` 语义（挂起仍只转状态；断点由检查点承载）。
- 不新增配置键；不改成功路径事件序列；不改子任务超时（`SUBTASK_TIMEOUT`）路径。
- 不删除已持久化的检查点文件（「按策略清理」维持既有 tracker 释放口径）。
