## MODIFIED Requirements

### Requirement: 后台任务跨重启登记与重入队

系统 SHALL 把后台子 Agent 任务的元数据**持久化**于状态目录
（`background-tasks.json`，`0600`、原子替换），字段 SHALL 限于
`task_id / agent_id / task / status / started_at / finished_at / session_id / error /
owner_pid / owner_start`；`task` 与 `error` SHALL 经密钥形态脱敏并有界。`owner_pid` SHALL
为启动该任务的进程 pid，`owner_start` SHALL 为该进程的启动标识（平台可取得时非空）。
`owner_pid / owner_start` SHALL NOT 对模型暴露。登记 SHALL 有界（最多保留最新 64 条），
文件损坏 SHALL 告警后按空登记处理，SHALL NOT 阻断启动或主循环。

重启加载时，落盘状态为 `running` 的任务 SHALL 按 owner 存活情况处理：owner 已退出、
owner 信息缺失（旧格式）或 pid 存活但启动标识不符（pid 复用）时，SHALL 映射为终态
`interrupted`（`error` 标记「进程重启导致中断」）；owner 仍存活时，SHALL 保持 `running`，
SHALL NOT 映射为 `interrupted`，SHALL NOT 由本进程取消或接管，也 SHALL NOT 重放完成通知
（该任务 SHALL 可由 `tools.tasks` 查询；`tools.task_retry` 按 running 规则拒绝）。
`interrupted` SHALL NOT 占用运行中上限。

登记写入 SHALL 在短独占建议锁内完成（同目录 `.{文件名}.lock`，POSIX `flock` / Windows
`msvcrt.locking`），并 SHALL 在锁内重新读取磁盘登记后**合并**写入：本实例变更过的条目
覆盖磁盘版本，未变更条目 SHALL 保留磁盘版本 —— 并发进程的登记与更新 SHALL NOT 被覆盖或
回滚；取锁失败 SHALL 降级为直接写入，SHALL NOT 阻断任务。写侧 SHALL 仍按 `started_at`
保留最新 64 条。

系统 SHALL 提供模型侧重入队工具 `tools.task_retry`：对 `interrupted / failed / cancelled`
任务，按登记的任务正文重新匹配子 Agent 并启动新的后台任务，返回新 `task_id`；
对 `running`（仍在执行）与 `done`（已完成）SHALL 结构化拒绝（`ok=false`）。
重入队 SHALL 恢复原会话归属；达到运行中上限时 SHALL 返回结构化失败。
`tools.task_retry` SHALL 判 `HIGH_RISK`（需人工审批），coeffect SHALL 为 `task:write`，
且 SHALL 只挂主工具面 —— 子 Agent SHALL NOT 可见。

#### Scenario: 终态跨重启可见

- **GIVEN** 一个后台任务已落终态（done / failed / cancelled）且登记已落盘
- **WHEN** 新进程构造注册表
- **THEN** `tools.tasks` SHALL 返回该任务及其终态，任务正文与错误 SHALL 有界且已脱敏

#### Scenario: 重启把运行中任务标记为被中断

- **GIVEN** 登记文件中存在 `status=running` 的任务，其 owner 进程已退出或 owner 信息缺失
- **WHEN** 新进程构造注册表
- **THEN** 该任务状态 SHALL 为 `interrupted`，`finished_at` SHALL 保持空
- **AND THEN** 系统 SHALL NOT 自动重执行该任务，SHALL NOT 投递完成通知

#### Scenario: 存活 owner 的在途任务不被误标

- **GIVEN** 登记文件中存在 `status=running` 的任务，其 `owner_pid` 存活且 `owner_start` 一致
- **WHEN** 另一进程构造注册表
- **THEN** 该任务状态 SHALL 保持 `running`，`finished_at` SHALL 保持空
- **AND THEN** SHALL NOT 投递完成通知，SHALL NOT 由本进程取消；`tools.task_retry` SHALL
  按 running 拒绝

#### Scenario: pid 复用不被误判为存活

- **GIVEN** 登记文件中存在 `status=running` 的任务，其 `owner_pid` 对应当前存活进程但
  `owner_start` 与当前进程启动标识不一致
- **WHEN** 构造注册表
- **THEN** 该任务 SHALL 映射为 `interrupted`（不把复用 pid 的无关进程当作 owner）

#### Scenario: 并发写不丢登记且不回滚新状态

- **GIVEN** 两个注册表实例共享同一状态文件，实例 B 已加载；随后实例 A 新增或更新了条目
- **WHEN** 实例 B 写入自己的条目
- **THEN** A 写入的条目与更新 SHALL 保留在状态文件中（不被 B 的陈旧快照覆盖）
- **AND THEN** 写侧 SHALL 在锁内按 `started_at` 保留最新至多 64 条

#### Scenario: 重入队被中断的任务

- **GIVEN** 一个 `interrupted`（或 `failed` / `cancelled`）的后台任务且存在可匹配子 Agent
- **WHEN** 模型调用 `tools.task_retry(task_id=...)` 并通过审批
- **THEN** 工具 SHALL 启动新的后台任务并返回新 `task_id` 与 `status="running"`
- **AND THEN** 原任务终态 SHALL 保持不变

#### Scenario: 运行中或已完成的任务拒绝重入队

- **GIVEN** 目标任务状态为 `running` 或 `done`
- **WHEN** 模型调用 `tools.task_retry`
- **THEN** 工具 SHALL 返回 `ok=false`，SHALL NOT 启动新任务

#### Scenario: 登记有界且损坏容忍

- **GIVEN** 登记文件损坏（坏 JSON / 结构不符）
- **WHEN** 新进程构造注册表
- **THEN** SHALL 告警一次并按空登记处理，启动 SHALL 继续
- **AND THEN** 登记条目数 SHALL 不超过 64 条（超出淘汰最旧）

#### Scenario: 登记不含密钥明文

- **GIVEN** 委托任务正文含密钥形态子串
- **WHEN** 登记落盘
- **THEN** 状态文件中 SHALL NOT 出现该密钥明文
