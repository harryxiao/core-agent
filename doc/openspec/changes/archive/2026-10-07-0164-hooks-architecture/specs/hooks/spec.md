## ADDED Requirements

### Requirement: 钩子事件面与载荷

系统 SHALL 提供 **7 个**钩子事件：`session.start` / `session.end` / `turn.before` / `turn.after` /
`tool.before` / `tool.after` / `memory.write`。每个事件 SHALL 携带**稳定 JSON 载荷**（字段名与语义为契约，
新增可选字段不视为破坏性变更）。

载荷 SHALL 先**逐条脱敏**再出进程边界：口令形态的值 SHALL ONLY 出现为 `<redacted>`，
SHALL NOT 出现任何密钥的 `${VAR}` **解析结果**。`tool.*` 的载荷 SHALL ONLY 提供参数 / 结果的
**摘要**（长度 + 哈希前缀），SHALL NOT 提供其正文。

**终止动作**（空 `tool_id`，即本轮回复）SHALL NOT 触发 `tool.before` / `tool.after`（与既有
`action_observers` 同口径）。

`memory.write` SHALL ONLY 可观察、SHALL NOT 可否决（记忆是进化轨迹载体，静默丢弃写入即轨迹断点）。

#### Scenario: 事件面完整

- **GIVEN** 钩子已启用且各事件均已声明钩子
- **WHEN** 会话建立 → 一轮开始 → 一个非终止动作执行 → 该轮收尾 → 一次记忆写入 → 会话结束
- **THEN** 七个事件各被投递一次，且载荷字段与契约表逐项一致

#### Scenario: 载荷不含密钥值

- **GIVEN** 某一环境变量（如 `CORE_HOOK_KEY`）已在配置中作为密钥引用且可解析
- **WHEN** 任一钩子事件被投递（载荷中含该引用的**使用位置**）
- **THEN** 载荷中 SHALL ONLY 出现 `${VAR}` **引用名**，SHALL NOT 出现其解析结果

#### Scenario: 记忆写入不可否决

- **GIVEN** `memory.write` 已声明一个退出码非 0 的钩子
- **WHEN** 内核写入一条记忆
- **THEN** 写入 SHALL 照常完成；钩子的非 0 退出码 ONLY 留痕

### Requirement: 钩子形态与接缝

钩子 SHALL 有且仅有**两种形态**：① **外部命令**（argv 列表、**不经 shell**，单事件 JSON 投递 stdin
后即 EOF）；② **内置回调**（组合根代码注入）。两者 SHALL 遵循**同一**失败语义。

外部命令的**退出码**语义：`before` 类（`turn.before` / `tool.before`）`0` 表示放行、**非 0 表示阻断**；
`after` 类（`session.*` / `turn.after` / `tool.after` / `memory.write`）的退出码 SHALL ONLY 留痕、
SHALL NOT 改变本轮结局。

系统 SHALL **复用既有横切接缝**消费这些事件（`tool.before` 经动作前链、`tool.after` 经结果侧观察者、
`turn.after` 经每轮收尾观察者），SHALL NOT 引入通用事件总线；当前无注入点的三个事件
（`turn.before` / `session.*` / `memory.write`）SHALL 以**新增注入形参**落地，SHALL NOT 在既有
`middlewares` 或 store 内部硬插分支。

#### Scenario: `tool.before` 钩子可阻断

- **GIVEN** `tool.before` 声明了一个退出码非 0 的钩子
- **WHEN** 内核尝试执行该非终止动作
- **THEN** 动作 SHALL NOT 执行，本轮以**已拒绝**的回复终止（与中间件拒绝同语义）
- **AND THEN** trace 中 SHALL 留有 `blocked_by` 标识该钩子

#### Scenario: 钩子复用既有接缝而非总线

- **GIVEN** 钩子已启用
- **WHEN** 审查 `tool.before` / `tool.after` / `turn.after` 的生产装配
- **THEN** 三者 SHALL 分别挂在既有 `middlewares` / `action_observers` / 每轮收尾观察者上，
  系统 SHALL NOT 存在事件总线组件

#### Scenario: 外部命令协议

- **GIVEN** 一个 `tool.before` 外部命令钩子
- **WHEN** 事件被投递
- **THEN** 该进程 SHALL 以 argv 列表启动（不经 shell）、stdin 收到**一个** JSON 信封后即 EOF

### Requirement: 钩子失败处置与安全边界

`before` 类钩子**超时**、**无法执行**（`OSError`）或**回调抛错**时，系统 SHALL 按该项的 `on_error`
处置，其**缺省值为 `block`**（fail-closed）；`after` 类钩子的任何异常 SHALL ONLY 留痕、
SHALL NOT 改变本轮结局。

钩子子进程 SHALL 以**白名单环境**启动，SHALL NOT 继承父进程环境中的密钥（密钥只经 coeffect 引用）。
钩子的 stdout / stderr SHALL **有界**（截断）且 SHALL NOT 进入日志 / 记忆 / 对话。

钩子副作用 SHALL NOT 纳入 `EffectTracker`（外部命令不可撤销）—— 此为本系统对「一切副作用可逆」的
**显式例外**；每次调用 SHALL 落 trace（`kind="hook"`，含事件名、命令 basename、退出码、时长），
SHALL NOT 记录完整 argv 与输出正文。

#### Scenario: `after` 钩子异常只留痕

- **GIVEN** `turn.after` 声明的钩子抛错 / 超时 / 退出码非 0
- **WHEN** 该轮收尾
- **THEN** 本轮结局（回复与终止语义）SHALL **逐字不变**，异常 ONLY 留痕

#### Scenario: `before` 钩子超时按 `on_error`

- **GIVEN** `tool.before` 钩子 `timeout_s=1`，缺省 `on_error`
- **WHEN** 该钩子超过 1s 未结束
- **THEN** 钩子进程被终止，动作 SHALL **被阻断**（`block` 为缺省）；若该项显式配 `allow`
- **AND THEN** 动作放行且 SHALL 留有 `hook_error` 痕

#### Scenario: 钩子不继承密钥环境且输出不回灌

- **GIVEN** 父进程环境中存在密钥解析结果
- **WHEN** 钩子子进程启动并输出一段文本
- **THEN** 子进程环境 SHALL NOT 含该密钥；其 stdout / stderr SHALL NOT 出现在日志 / 记忆 / 对话中

#### Scenario: 钩子副作用不纳入可逆效应追踪

- **GIVEN** 一个会产生文件副作用的钩子
- **WHEN** 本轮结束执行回滚（`EffectTracker` 撤销）
- **THEN** 系统 SHALL NOT 尝试撤销该钩子的副作用（契约明示：这是可逆性的**显式例外**）

### Requirement: 钩子声明面

钩子 SHALL 经**配置单一真源**（`configuration` 的 `ConfigSpec`）声明：**标量项**
（`hooks.enabled` / `hooks.timeout_s` / `hooks.on_error`）SHALL 支持 **CLI flag / 环境变量 / `config.yaml`
三层**，优先级链为 **CLI flag > 环境变量 > `config.yaml` > 默认值**；**钩子清单**（`hooks.entries`）
SHALL ONLY 从 `config.yaml` 的结构化段读取（不提供 flag / 环境变量形态）。

`hooks.enabled` 缺省 SHALL 为**关闭**（未显式开启不加载、不执行任何钩子）。`timeout_s` 的**硬上限**
SHALL 为 60 秒 —— 配置超上限 SHALL 按上限截断并告警，SHALL NOT 接受无界超时。

#### Scenario: 标量配置三层优先级

- **GIVEN** 同一标量项在 `config.yaml`、环境变量与 CLI flag 三处都有取值
- **WHEN** 解析 `hooks.timeout_s`
- **THEN** 取值 SHALL 为 CLI flag 的值；移去 flag 后 SHALL 为环境变量的值；再移去后 SHALL 为
  `config.yaml` 的值；三者皆缺时 SHALL 为默认值

#### Scenario: 钩子清单只走配置文件

- **GIVEN** `hooks.entries` 在 `config.yaml` 中声明了两条钩子
- **WHEN** 内核装配钩子
- **THEN** 两条 SHALL 各自生效；系统 SHALL NOT 提供 `hooks.entries` 的 CLI flag 或环境变量形态

#### Scenario: 缺省关闭与超时硬上限

- **GIVEN** `config.yaml` 未声明 `hooks` 段（或 `enabled: false`），以及另一配置将 `timeout_s` 配成 3600
- **WHEN** 内核装配钩子
- **THEN** 前者 SHALL **不执行**任何钩子；后者的生效超时 SHALL 被截断为 60s 并告警
