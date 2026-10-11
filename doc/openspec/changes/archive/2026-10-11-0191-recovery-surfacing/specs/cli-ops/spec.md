# CLI-Ops Specification Delta — 入口启动呈现未完成任务 + 续跑取最新检查点（change 0191）

## MODIFIED Requirements

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

一次性**任务**入口（`task <目标>`）新任务铸会话时 SHALL 经**同一**跨进程共享注册表登记
（mode `cli`，不另建第二注册表）—— 铸出的会话对 `session list` 可见、对交互入口 `--session`
续接可用；任务续跑（`--resume`）SHALL 复用检查点携带的既有会话（SHALL NOT 另铸新会话导致
同一任务轨迹分裂）。

一次性任务入口（`task <目标>`，新任务）与常驻**服务**入口（`serve`）**启动时** SHALL 扫描检查点并
**呈现**未完成任务（告警 + 提示 `task --resume <id>` 可续跑），SHALL NOT 自动重新执行未完成任务
（副作用不自动重放）；呈现 SHALL NOT 改变运行态、SHALL NOT 阻塞入口启动。任务续跑（`--resume`）
SHALL 取**时间戳最新**的检查点重建续跑状态（与崩溃恢复取最近有效检查点同口径）。

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

#### Scenario: 一次性任务入口铸会话入同一注册表
- **GIVEN** 操作者执行 `core-agent task <目标>`（新任务）
- **WHEN** 任务开始执行
- **THEN** 铸出的会话经共享注册表登记（mode `cli`），`session list` 可见；续跑 `--resume` 复用检查点既有会话而非另铸

#### Scenario: 入口启动呈现未完成任务
- **GIVEN** 存在未完成任务（检查点无 done 标记）
- **WHEN** 启动 `task` 或 `serve` 入口
- **THEN** 打印未完成任务标识与续跑提示（`task --resume <id>`），不自动重新执行、不阻塞入口启动

#### Scenario: 续跑取时间戳最新检查点
- **GIVEN** 同一任务的多个检查点，其落盘次序与时间戳次序不一致
- **WHEN** 执行 `core-agent task --resume <task-id>`
- **THEN** 取时间戳最新的检查点重建续跑状态（与崩溃恢复 restore 同口径）
