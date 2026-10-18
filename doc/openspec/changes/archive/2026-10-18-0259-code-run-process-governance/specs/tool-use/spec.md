## MODIFIED Requirements

### Requirement: 超时与资源上限
系统 SHALL 为工具执行设置超时/资源上限，异常不拖垮主循环；子进程类工具在超时或取消时 SHALL
终止**整棵进程树**，SHALL NOT 只终止直接子进程而放任后代继续运行。

- 工具外层超时由 `ToolProvider` 的 `asyncio.wait_for` 兜底，超时归一为结构化 `TIMEOUT`。
- `tools.code_run` 的脚本级超时 SHALL 同样归一为 `TIMEOUT`（不再归为 `EXECUTION_FAILED`）。
- `tools.code_run` 的 `timeout` SHALL 接受 `(0, 600]` 内的有限秒数；非有限数或越界 SHALL
  结构化拒绝（`EXECUTION_FAILED`，带明确原因），SHALL NOT 启动子进程。
- POSIX 宿主 SHALL 以独立会话 / 进程组启动子进程，终止时按进程组发送信号；Windows 宿主 SHALL
  以新进程组启动，并以系统 `taskkill /T /F` 递归终止进程树。
- 超时或协程取消后 SHALL 先终止进程树并回收子进程，再返回；SHALL NOT 遗留仍可写文件的子进程。

#### Scenario: 执行超时
- **GIVEN** 一个工具调用正在执行
- **WHEN** 执行超过超时阈值
- **THEN** 强制终止该调用并返回超时错误（`TIMEOUT`），主循环继续运行

#### Scenario: 子进程超时终止整棵进程树
- **GIVEN** `tools.code_run` 启动的脚本派生了一个孙进程（如后台命令），且脚本超过 `timeout`
- **WHEN** 超时触发
- **THEN** 直接子进程与孙进程 SHALL 均被终止，孙进程不得在超时后继续产生副作用；
  调用返回 `TIMEOUT`

#### Scenario: 调用被取消同样终止进程树
- **GIVEN** `tools.code_run` 正在执行
- **WHEN** 上层取消该调用（`CancelledError`，如主循环中断）
- **THEN** 进程树被终止并回收，取消继续向上传播

#### Scenario: 超时参数越界拒绝
- **GIVEN** `timeout` 为 `0`、负数、`inf` 或大于 600
- **WHEN** 调用 `tools.code_run`
- **THEN** 返回 `EXECUTION_FAILED` 且不启动子进程

#### Scenario: 执行异常兜底
- **GIVEN** 工具 handler 执行中抛出异常（如参数值合法但语义非法，底层库报错）
- **WHEN** 调用经 ToolProvider 执行
- **THEN** 异常归一为 EXECUTION_FAILED 结构化错误返回，主循环继续运行，不向模型抛裸异常

#### Scenario: 资源上限
- **GIVEN** 一个工具调用申请资源（内存 / CPU / 子进程）
- **WHEN** 资源占用超过上限
- **THEN** 限制或终止该调用，防止拖垮主循环

## ADDED Requirements

### Requirement: 后台命令执行与进程管理

系统 SHALL 提供后台命令执行能力与配套的进程巡检 / 终止工具，使长命令不阻塞主循环。

- `tools.code_run` SHALL 接受 `background: boolean`（缺省 `false`）；为 `true` 时 SHALL 立即返回
  `pid` 与系统生成的输出文件路径，命令的 stdout 与 stderr 合并写入该文件；`timeout` 对后台
  任务不适用。输出文件 SHALL 以仅属主可读写（0600）创建，路径 SHALL 位于
  `$CORE_STATE_DIR`（缺省 `~/.core/state`）下的运行目录（0700）；SHALL NOT 接受模型指定的
  输出路径。
- 系统 SHALL 维护**本进程启动的**后台任务注册表（有界），记录 pid、输出文件、启动时间与退出码
  状态；SHALL NOT 记录脚本正文。注册表满且无已退出项可淘汰时 SHALL 拒绝新后台任务。
- `tools.process` SHALL 提供 `list`（全部后台任务）、`status`（按 pid）、`output`（按 pid 读取
  输出文件尾部，有界）三个动作；SHALL 为只读工具（可逆、`process:read` coeffect）。
- `tools.process_kill` SHALL 按 pid 终止注册表内的后台任务进程树；SHALL 为不可逆工具
  （`process:write` coeffect），经确认门约束。注册表外的 pid SHALL 拒绝，SHALL NOT 终止任意
  系统进程。
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
