# Spec Delta — ui（0314 TUI 退出不等待在途工作）

## ADDED Requirements

### Requirement: TUI 退出及时性

TUI 用户请求退出（Ctrl+Q）时，进程 SHALL 及时结束：退出路径 SHALL NOT 等待**在途阻塞工作**
（默认执行器线程中的 LLM 流读取、工具执行、钩子外呼等）完成，SHALL NOT 让退出耗时随在途
工作的**剩余时长**增长。

退出 SHALL 保留既有收尾语义：Textual worker SHALL 照常被取消、终端状态 SHALL 照常复原、
解释器级清理（`atexit` 注册的钩子 `close` / MCP 子进程回收 / 插件卸载）SHALL 照常执行。
被放弃的在途工作 SHALL 随进程终止，SHALL NOT 阻塞退出。

空闲退出与一轮正常完成后的退出 SHALL 与既有行为一致。Ctrl+B 打断（停本轮）与 Ctrl+Q
退出（结束进程）语义 SHALL 保持分离。

#### Scenario: 在途阻塞工作不阻塞退出
- **GIVEN** TUI 正有一轮在途，且其工作线程阻塞在长读（如 LLM 流式响应 / 工具执行）
- **WHEN** 用户按 Ctrl+Q
- **THEN** 进程在**与在途工作剩余时长无关**的短时间内结束；终端状态复原；退出码为 0

#### Scenario: 空闲退出逐字不变
- **GIVEN** TUI 空闲（无在途轮次）
- **WHEN** 用户按 Ctrl+Q
- **THEN** 进程立即结束，行为与既有实现一致

#### Scenario: 打断与退出语义分离
- **GIVEN** TUI 正有一轮在途
- **WHEN** 用户按 Ctrl+B
- **THEN** 仅打断本轮（进程继续运行）；Ctrl+Q 才结束进程
