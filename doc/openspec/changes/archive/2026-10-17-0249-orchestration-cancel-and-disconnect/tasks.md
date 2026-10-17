# Tasks 0249: 运行中取消与消费方断流

- [ ] 1. **T1 取消信号**：调度器登记 `_cancel_events` / `_wave_tasks`；`cancel` 置信号、
      取消在途 fan-out、终态幂等。
- [ ] 2. **T2 执行流观察**：`astream` 薄包装 + `_stream_task` 检查点；`TASK_CANCELLED` 终态事件。
- [ ] 3. **T3 fan-out 回收**：`_stream_wave` 注册/取消/回收；协作取消安静收拢，外部取消透传。
- [ ] 4. **T4 终态释放**：`_release` 清理 `_results` / 信号 / 在途登记；断流转 `FAILED`。
- [ ] 5. **T5 规格与测试**：spec delta（4 Scenario）；取消打断 / 断流回收 / 终态清理 / 幂等四组用例；
      四门禁全绿。
- [ ] 6. **T6 收尾**：`openspec validate --all`（本 change 绿）、归档、ADR / 台账 / 测试节 / 接口文档、
      单次提交。
