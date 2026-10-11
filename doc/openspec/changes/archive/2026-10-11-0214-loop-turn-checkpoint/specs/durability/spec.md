# Durability Specification Delta — 主循环会话轮级检查点（change 0214）

## ADDED Requirements

### Requirement: 会话轮级检查点
系统 SHALL 支持**会话轮级检查点**（turn checkpoint）：主循环（main loop）在**轮首**（感知完成、
进入推理之前）与**轮末**（收尾记忆写回之后）各写一次检查点，两次 SHALL 以**同一** task id
（命名空间 `turn.<trace_id>`）承载该轮的**在途**态与**完结**态。轮首写入的状态 SHALL 标记该轮
**未完结**并携带轮目标与会话归属；轮末写入 SHALL 标记该轮**已完结**。

轮级检查点 SHALL 由配置 `loop.turn_checkpoint`（布尔，缺省 `false`）门控：**缺省关**时主循环
SHALL NOT 写入任何轮级检查点（既有路径**逐字不变**、零 I/O、零副作用）。

轮级检查点的写入 SHALL **不影响本轮结局**：写入失败（持久化不可用）SHALL 只记录告警，
SHALL NOT 中断当前轮、SHALL NOT 改变本轮成败记账。

轮级检查点 SHALL 使用**独立 task id 命名空间**（前缀 `turn.`），使启动恢复扫描能将其与编排
任务（orchestration task）识别区分。该命名空间 SHALL NOT 被任务续跑命令承接 —— 会话轮
SHALL NOT 通过 `task --resume` 恢复（**续聊即恢复**，轮级检查点**只**用于呈现「上次有哪些轮
被中断」）。

启动恢复扫描 SHALL 对轮级检查点**独立呈现**：呈现被中断的会话轮（数量与所属会话），
SHALL NOT 提示续跑命令，且 SHALL NOT 与编排任务的续跑句柄混列。

轮级检查点 SHALL NOT 携带撤销账本（undo ledger）：其状态快照 SHALL 仅承载**呈现**所需的轮级
信息（轮目标 / 是否完结），SHALL NOT 声称可用于重放。

#### Scenario: 轮首写入在途标记
- **GIVEN** 轮级检查点已启用（`loop.turn_checkpoint: true`），主循环开始一轮
- **WHEN** 感知完成、进入推理之前
- **THEN** 以 `turn.<trace_id>` 写入一个检查点，其状态标记该轮**未完结**，并携带轮目标与会话归属

#### Scenario: 轮末写入完结标记
- **GIVEN** 同一轮执行完毕（含达到循环上限的终止轮）
- **WHEN** 收尾记忆写回之后
- **THEN** 以**同一** `turn.<trace_id>` 写入检查点，其状态标记该轮**已完结**

#### Scenario: 中途中断留未完结态
- **GIVEN** 一轮在推理或行动**中途**被中断（进程被杀或抛错）
- **WHEN** 启动扫描读取该会话轮的检查点
- **THEN** 该轮的最新快照仍为**未完结**（不误报完结、不谎报成功）

#### Scenario: 启动扫描独立呈现不提示续跑
- **GIVEN** 存在未完结的会话轮检查点，且另有未完成的编排任务
- **WHEN** 启动恢复扫描呈现结果
- **THEN** 被中断的会话轮被**独立**呈现（数量与所属会话），**不**提示 `task --resume`；
  编排任务照旧获得其续跑命令提示；两者不混列

#### Scenario: 缺省关零写入
- **GIVEN** 未启用 `loop.turn_checkpoint`（缺省）
- **WHEN** 主循环执行若干轮
- **THEN** 不产生任何 `turn.` 命名空间的检查点（既有路径逐字不变、零 I/O）
