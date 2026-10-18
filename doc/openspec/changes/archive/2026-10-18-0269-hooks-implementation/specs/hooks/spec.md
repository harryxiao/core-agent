## MODIFIED Requirements

### Requirement: 钩子形态与接缝

钩子 SHALL 有且仅有**两种形态**：① **外部命令**（argv 列表、**不经 shell**，单事件 JSON 投递 stdin
后即 EOF）；② **内置回调**（组合根代码注入）。两者 SHALL 遵循**同一**失败语义。

外部命令的**退出码**语义：`before` 类（`turn.before` / `tool.before`）`0` 表示放行、**非 0 表示阻断**；
`after` 类（`session.*` / `turn.after` / `tool.after` / `memory.write`）的退出码 SHALL ONLY 留痕、
SHALL NOT 改变本轮结局。

系统 SHALL **复用既有横切接缝**消费这些事件（`tool.before` 经动作前链、`tool.after` 经结果侧观察者、
`turn.after` 经每轮收尾的**同步注入点**；后台 `turn_observer` 保持既有「收尾后异步观察」语义不变），
SHALL NOT 引入通用事件总线；`turn.before` / `session.*` / `memory.write` 以及 `turn.after` 的同步
注入点 SHALL 以**新增注入形参**落地，SHALL NOT 在既有 `middlewares` 或 store 内部硬插分支。

#### Scenario: `tool.before` 钩子可阻断

- **GIVEN** `tool.before` 声明了一个退出码非 0 的钩子
- **WHEN** 内核尝试执行该非终止动作
- **THEN** 动作 SHALL NOT 执行，本轮以**已拒绝**的回复终止（与中间件拒绝同语义）
- **AND THEN** trace 中 SHALL 留有 `blocked_by` 标识该钩子

#### Scenario: 钩子复用既有接缝而非总线

- **GIVEN** 钩子已启用
- **WHEN** 审查 `tool.before` / `tool.after` / `turn.after` 的生产装配
- **THEN** `tool.before` / `tool.after` SHALL 分别挂在既有 `middlewares` / `action_observers` 上，
  `turn.after` SHALL 挂在每轮收尾的同步注入点（与后台观察者分列，原因：trace 封口顺序），
  系统 SHALL NOT 存在事件总线组件

#### Scenario: 外部命令协议

- **GIVEN** 一个 `tool.before` 外部命令钩子
- **WHEN** 事件被投递
- **THEN** 该进程 SHALL 以 argv 列表启动（不经 shell）、stdin 收到**一个** JSON 信封后即 EOF
