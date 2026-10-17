## ADDED Requirements

### Requirement: 流式增量等待超时

流式调用 SHALL 对**相邻增量之间的等待**（含首块）施加上限：等待超过构造注入的 `timeout`
（缺省 `60.0` 秒，与「模型调用可靠性」同源）且队列无新增量时，系统 SHALL 判定为流式超时，
归一为 `LLMTimeoutError` 并尽力释放底层响应，SHALL NOT 让调用方无限挂起。该上限 SHALL
覆盖「连接仍存活但只发 SSE 注释 / keep-alive、不产出任何增量」的情形。

超时前已外发的增量 SHALL 保持已交付（与「流式断流处理」的部分返回语义一致）；流式调用
SHALL NOT 因超时自动重试（已外发内容不可撤销，重试会重复 / 乱序正文）。增量持续到达时
SHALL NOT 触发该超时（不设总时长上限）。

#### Scenario: 连接存活但无增量时超时
- **GIVEN** 流式响应已建立，端点在 `timeout` 内不产出任何增量（仅注释 / keep-alive）
- **WHEN** 调用方等待下一增量
- **THEN** 等待超过 `timeout` 后抛出 `LLMTimeoutError`，调用方不再无限挂起

#### Scenario: 增量持续到达不误杀
- **GIVEN** 流式响应按次序返回多个增量，相邻间隔均小于 `timeout`
- **WHEN** 调用方逐块消费
- **THEN** 全部增量正常返回，不触发超时
