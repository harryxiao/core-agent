## ADDED Requirements

### Requirement: 未完成任务自动续跑

系统 SHALL 提供**显式开启**的未完成任务自动续跑：配置 `orchestration.auto_resume`
（默认 `false`）开启后，`core-agent task` 启动路径 SHALL 扫描检查点，对未完成
（`done=false`）的编排任务重建计划 / 已完成子任务集 / 交接结果 / 发起会话标识并续跑。

- 自动续跑 SHALL 跳过：已完成（`done=true`）任务、会话轮级检查点（`task_id` 以 `turn.` 开头
  或状态标记 `kind=turn`）、以及缺少可解析计划或快照损坏者（降级跳过并告警，
  SHALL NOT 中断其余任务）。
- 自动续跑 SHALL **有界**：同一任务跨进程最多 **3** 次自动尝试；两次尝试间 SHALL 指数退避
  （首次尝试后 60s、随后每次翻倍，上限 `3600s`），计数与时间戳 SHALL 持久化于状态目录
  （`auto-resume.json`，`0600`，不含任务正文 / 记忆 / 密钥）。达到上限 SHALL 跳过并告警，
  SHALL NOT 删除检查点；人工 `task --resume <id>` SHALL 不受该上限与退避约束。
- 续跑失败 SHALL 保留检查点，使下次启动可在退避后重试。
- `auto_resume=false` 时启动路径 SHALL 维持既有「纯扫描 + 呈现」语义，SHALL NOT 自动重执行。
- `core-agent task --resume-all` SHALL 作为显式入口续跑全部未完成任务，SHALL 不受配置开关与
  退避 / 上限约束。

#### Scenario: 默认关闭只呈现
- **GIVEN** `orchestration.auto_resume=false` 且存在未完成编排任务
- **WHEN** 执行 `core-agent task <新目标>`
- **THEN** 只呈现「未完成任务 / `task --resume <id>`」提示，不自动续跑，且新目标照常执行

#### Scenario: 开启后自动续跑
- **GIVEN** `auto_resume=true`，检查点含未完成任务（计划 / 已完成子任务 / 交接结果 / 会话标识）
- **WHEN** 执行 `core-agent task <新目标>`
- **THEN** 先按检查点重建并续跑未完成任务，已完成子任务不重复执行，再执行新目标

#### Scenario: 跳过不可续跑项
- **GIVEN** 检查点分别属于已完成任务、会话轮级检查点、以及无计划的坏快照
- **WHEN** 自动续跑扫描
- **THEN** 三类均不被续跑；坏快照降级告警且不影响其余任务

#### Scenario: 自动尝试有界
- **GIVEN** 同一未完成任务已自动尝试 3 次且仍失败
- **WHEN** 再次启动
- **THEN** 该任务被跳过并告警，检查点保留；人工 `task --resume <id>` 仍可执行
