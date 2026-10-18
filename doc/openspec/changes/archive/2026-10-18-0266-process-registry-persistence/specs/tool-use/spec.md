## MODIFIED Requirements

### Requirement: 后台命令执行与进程管理

系统 SHALL 提供后台命令执行能力与配套的进程巡检 / 终止工具，使长命令不阻塞主循环。

- `tools.code_run` SHALL 接受 `background: boolean`（缺省 `false`）；为 `true` 时 SHALL 立即返回
  `pid` 与系统生成的输出文件路径，命令的 stdout 与 stderr 合并写入该文件；`timeout` 对后台
  任务不适用。输出文件 SHALL 以仅属主可读写（0600）创建，路径 SHALL 位于
  `$CORE_STATE_DIR`（缺省 `~/.core/state`）下的运行目录（0700）；SHALL NOT 接受模型指定的
  输出路径。
- 系统 SHALL 维护**有界**的后台任务注册表，记录本进程启动的后台任务，并在进程重启后恢复先前
  登记的条目；每条记录 pid、输出文件、启动时间、运行类型、进程启动标识（可用时）与退出码状态
  （仅本进程任务）；SHALL NOT 记录脚本正文、命令或环境变量。注册表满且无已退出项可淘汰时
  SHALL 拒绝新后台任务。
- 注册表 SHALL 把上述元数据**原子**写入 `$CORE_STATE_DIR` 下的 `processes.json`
  （仅属主可读写 0600）；写入失败 SHALL NOT 阻止后台任务启动与登记。加载时文件缺失、损坏或
  条目非法 SHALL 按空注册表 / 跳过该条处理，SHALL NOT 阻断注册表使用；恢复条目数 SHALL
  遵守注册表上界（保留最新条目）。
- 构造注册表时 SHALL 恢复登记项为**恢复项**（无进程句柄）；`tools.process` 的 `list` /
  `status` / `output` 对恢复项 SHALL 可用，结果 SHALL 带 `restored=true`。恢复项存活 SHALL
  以 `kill(pid, 0)` 探测；Linux 上 SHALL 再与 `/proc/<pid>/stat` 的进程启动时刻比对，
  不符（PID 复用）SHALL 判为已退出。恢复项的退出码 SHALL 为 `null`。
- `tools.process` SHALL 提供 `list`（全部后台任务）、`status`（按 pid）、`output`（按 pid 读取
  输出文件尾部，有界）三个动作；SHALL 为只读工具（可逆、`process:read` coeffect）。
- `tools.process_kill` SHALL 按 pid 终止**本进程启动的**注册表内后台任务进程树；SHALL 为
  不可逆工具（`process:write` coeffect），经确认门约束。恢复项 SHALL 拒绝终止并返回
  `killed=false` / `restored=true`，SHALL NOT 触达该进程；注册表外的 pid SHALL 拒绝，
  SHALL NOT 终止任意系统进程。
- 权限分级：工具标识中的 `process` 词元 SHALL 视为只读动作词（`tools.process` 判 `read`）；
  `tools.process_kill` 因含高危词元 `kill` SHALL 仍判 `high-risk`。

#### Scenario: 后台执行立即返回
- **GIVEN** Agent 需要运行耗时较长的命令
- **WHEN** 调用 `tools.code_run` 且 `background=true`
- **THEN** 调用立即返回 `pid` 与输出文件路径，命令在后台继续运行；`tools.process status`
  可按 pid 查到该任务

#### Scenario: 后台输出可读
- **GIVEN** 一个后台任务已产生输出
- **WHEN** 调用 `tools.process` 且 `action=output`、给出该 pid
- **THEN** 返回输出文件尾部（有界），不阻塞、不消耗该进程

#### Scenario: 终止后台任务
- **GIVEN** 一个由本进程启动的后台任务仍在运行
- **WHEN** 调用 `tools.process_kill` 并为该 pid 获得批准
- **THEN** 该任务及其后代被终止，`tools.process status` 显示已退出状态

#### Scenario: 未知 pid 拒绝
- **GIVEN** pid 不在本进程的后台任务注册表内
- **WHEN** 调用 `tools.process` 或 `tools.process_kill`
- **THEN** 返回 `found=false` 结构化结果，SHALL NOT触及该进程

#### Scenario: 后台任务不随调用返回被终止
- **GIVEN** `tools.code_run` 以 `background=true` 启动了一个任务
- **WHEN** 工具调用返回后主循环继续
- **THEN** 该后台任务持续运行，直至自行结束或被 `tools.process_kill` 终止

#### Scenario: 进程工具权限分级
- **GIVEN** 权限引擎对 `tools.process` 与 `tools.process_kill` 判级
- **WHEN** 执行前判定
- **THEN** `tools.process` 判为 `read` 并放行；`tools.process_kill` 判为 `high-risk`，
  未获审批时返回 `APPROVAL_REQUIRED`

#### Scenario: 重启后仍可巡检
- **GIVEN** 一个后台任务在 core-agent 上一进程退出后仍在运行，且其登记项已落盘
- **WHEN** 新进程构造注册表并调用 `tools.process`
- **THEN** `list` / `status` / `output` 仍可定位该任务（`restored=true`），运行中的任务
  `running=true`，输出文件尾部可读

#### Scenario: PID 复用不误报
- **GIVEN** 恢复项登记的进程启动时刻与当前 `/proc/<pid>/stat` 不符（pid 已被无关进程复用）
- **WHEN** 查询该恢复项状态
- **THEN** 返回 `running=false`，SHALL NOT 报告该无关进程为原后台任务

#### Scenario: 恢复项不可终止
- **GIVEN** 一个从磁盘恢复的登记项（无进程句柄）
- **WHEN** 调用 `tools.process_kill` 并为该 pid 获得批准
- **THEN** 返回 `found=true` / `killed=false` / `restored=true`，SHALL NOT 触达该进程

#### Scenario: 持久化文件损坏不阻断
- **GIVEN** `processes.json` 内容不是合法 JSON 或含非法条目
- **WHEN** 构造后台任务注册表
- **THEN** 加载不抛异常，非法条目被跳过，注册表可继续登记新任务
