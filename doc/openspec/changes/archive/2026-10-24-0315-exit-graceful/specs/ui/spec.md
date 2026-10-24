# Spec Delta — ui（0315 TUI 优雅退出 `/exit`）

## ADDED Requirements

### Requirement: TUI 优雅退出（`/exit`）

TUI SHALL 提供 `/exit` 斜杠命令：在无在途轮次时，命令 SHALL 先等待本会话**轮末后台收尾
链**（技能反馈 + 记忆压实/遗忘）收束，再正常退出；等待 SHALL 有界（复用既有轮末等待上限），
超时或收尾失败 SHALL 明示后仍正常退出，SHALL NOT 无限期挂起。

有在途轮次时 `/exit` SHALL 拒绝并提示（不排队、不放弃本轮）。`/exit` SHALL NOT 接受参数。
Ctrl+Q / Ctrl+C 的**立即退出**语义 SHALL 逐字不变。

#### Scenario: 空闲退出先收束后台收尾
- **GIVEN** 会话空闲，但上一轮的后台收尾链（记忆压实/遗忘、技能反馈）仍在途
- **WHEN** 用户输入 `/exit`
- **THEN** TUI 显示保存提示，等待该链收束后退出；退出码为 0

#### Scenario: 收尾超时仍退出
- **GIVEN** 后台收尾链超过既有等待上限仍未收束
- **WHEN** 用户输入 `/exit`
- **THEN** TUI 明示「收尾超时（已尽力保存）」后退出；进程不挂死，退出码为 0

#### Scenario: 在途轮次拒绝退出
- **GIVEN** TUI 正有一轮在途
- **WHEN** 用户输入 `/exit`
- **THEN** TUI 提示本轮进行中、需等本轮结束或按 Ctrl+Q 立即退出；不调用收尾等待、不退出

#### Scenario: Ctrl+Q 立即退出不变
- **GIVEN** 后台收尾链仍在途
- **WHEN** 用户按 Ctrl+Q
- **THEN** 进程立即结束，不等待收尾链（change 0314 语义）
