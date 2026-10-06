# CLI Ops Specification Delta

## ADDED Requirements

### Requirement: 会话命令族与交互入口续聊
系统 SHALL 提供会话命令族：`session create`（新建会话并返回标识，登记于跨进程共享注册表）、
`session list`（枚举已登记会话：标识 + 模式）、`session show <session_id>`（按追加次序打印该会话的
对话转录）。`session show` 的转录 SHALL 取自与内核回灌**同一**转录存储（不另建副本、不第二真源）；
该会话**无转录**时 SHALL 明示无记录并以退出码 0 结束（SHALL NOT 伪造内容）。**未登记于注册表**的
`session_id` SHALL 被拒绝（fail-closed：非零退出码 + 明确提示），SHALL NOT 放宽既有会话校验；
三者均为一次性动作，不改变运行态、不启动常驻进程。

交互入口（无子命令进入的会话循环）SHALL 接受 `--session <session_id>` 以**续接既有会话**：该标识
有效时 SHALL 复用（**SHALL NOT** 新建会话），且该会话既有转录 SHALL 被载入续聊上下文与呈现面；
该标识未登记时 SHALL fail-closed 拒绝。未指定 `--session` 时 SHALL 新建会话（既有行为不变）。

#### Scenario: 列出与查看会话转录
- **GIVEN** 已存在一个会话且其转录含若干轮对话
- **WHEN** 依次执行 `session list` 与 `session show <session_id>`
- **THEN** `list` 列出该会话标识与模式；`show` 按追加次序打印该会话的转录内容

#### Scenario: 查看无转录的会话
- **GIVEN** 一个已登记但尚无对话记录的会话
- **WHEN** 执行 `session show <session_id>`
- **THEN** 明示该会话无对话记录，并以退出码 0 结束（不伪造内容）

#### Scenario: 查看未登记会话被拒
- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 执行 `session show <session_id>`
- **THEN** 拒绝并提示该会话不存在，以非零退出码结束（fail-closed，不放宽会话校验）

#### Scenario: 交互入口续接既有会话
- **GIVEN** 一个已登记的会话，其转录已有若干轮
- **WHEN** 以 `--session <session_id>` 进入交互入口
- **THEN** 复用该会话标识（不新建），其既有转录被载入续聊上下文与呈现面

#### Scenario: 交互入口续接未登记会话被拒
- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 以 `--session <session_id>` 进入交互入口
- **THEN** fail-closed 拒绝（不静默新建会话顶替）
