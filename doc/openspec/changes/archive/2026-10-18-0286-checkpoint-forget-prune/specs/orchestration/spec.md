## ADDED Requirements

### Requirement: 检查点运维入口

系统 SHALL 提供两个显式 CLI 运维模式：`core-agent task --forget <task-id>` 与
`core-agent task --prune-checkpoints [--max-count N] [--older-than-s S]`。两者 SHALL 与
`<目标>`、`--resume`、`--resume-all`、`--task-id` 互斥；`--prune-checkpoints` SHALL 要求
`--max-count`（≥1 的整数）与 `--older-than-s`（≥0 的数值）至少给出一个，否则以用法错误
非零退出且不修改任何数据。两个模式 SHALL NOT 暴露为模型工具。

在读写 `$CORE_STATE_DIR/checkpoints.jsonl` **之前**，两个模式 SHALL 获取
`0285` 定义的续跑批次锁（`$CORE_STATE_DIR/.auto-resume.json.lock`）。锁忙或不可用时
SHALL fail-closed：不删除任何检查点、向 stderr 输出可检索前缀 `[checkpoints_locked]`、
以非零退出码结束。

`--forget <task-id>` SHALL 删除该任务 id 的**全部**检查点（包括 pinned），SHALL NOT 删除
其他任务 id 的检查点或会话轮检查点；随后 SHALL 清除 `auto-resume.json` 中该任务 id 的
退避/尝试记录。删除数量大于 0 时 SHALL 以退出码 0 结束；删除数量为 0 时 SHALL 以非零
退出码结束并提示未找到。输出 SHALL 只含任务 id 与计数，SHALL NOT 含任务目标、子任务回复
或任何密钥。

`--prune-checkpoints` SHALL 复用检查点保留语义：`--max-count N` 只清理**未 pinned** 的
最旧检查点，直到未 pinned 数量不超过 N；`--older-than-s S` 只清理时间戳早于
`当前时间 - S` 的**未 pinned** 检查点；两参数同时给出时两种条件同时生效；pinned 检查点
SHALL 永不被该模式删除。清理 SHALL 一次原子落盘。成功时 SHALL 以退出码 0 结束并输出
删除数、保留数与 pinned 数。

#### Scenario: 显式遗忘只删除目标任务

- **GIVEN** `checkpoints.jsonl` 中同时存在任务 `t1` 与 `t2` 的检查点，且 `auto-resume.json`
  中有 `t1` 的退避记录
- **WHEN** 执行 `core-agent task --forget t1`
- **THEN** `t1` 的全部检查点 SHALL 被删除，`t2` 的检查点 SHALL 保留
- **AND THEN** `t1` 的自动续跑退避记录 SHALL 被清除，退出码 SHALL 为 0

#### Scenario: 遗忘包含 pinned 且未知任务非零退出

- **GIVEN** 任务 `t1` 含一个 pinned 检查点；任务 `ghost` 不存在
- **WHEN** 分别执行 `task --forget t1` 与 `task --forget ghost`
- **THEN** 前者 SHALL 删除 pinned 检查点并以 0 退出
- **AND THEN** 后者 SHALL 不修改任何检查点，以非零退出并提示未找到

#### Scenario: 一次性清理保护 pinned

- **GIVEN** 多个未 pinned 检查点与一个最旧的 pinned 检查点
- **WHEN** 执行 `task --prune-checkpoints --max-count 2`
- **THEN** 未 pinned 检查点 SHALL 只保留最新 2 个，pinned 检查点 SHALL 保留
- **AND THEN** 输出 SHALL 含删除数、保留数与 pinned 数

#### Scenario: 时间窗口清理只删除陈旧未 pinned 检查点

- **GIVEN** 一个早于窗口的未 pinned 检查点与一个同样早于窗口的 pinned 检查点
- **WHEN** 执行 `task --prune-checkpoints --older-than-s 60`
- **THEN** 陈旧未 pinned 检查点 SHALL 被删除，pinned 检查点 SHALL 保留

#### Scenario: 续跑批次运行中拒绝维护

- **GIVEN** 另一进程持有 `.auto-resume.json.lock`
- **WHEN** 执行 `task --forget t1` 或 `task --prune-checkpoints --max-count 1`
- **THEN** SHALL 不修改任何检查点，stderr SHALL 含 `[checkpoints_locked]`
- **AND THEN** 退出码 SHALL 为非零

#### Scenario: 缺少清理边界不执行

- **GIVEN** 未给出 `--max-count` 或 `--older-than-s`
- **WHEN** 执行 `task --prune-checkpoints`
- **THEN** SHALL 以用法错误非零退出，且不修改任何检查点
