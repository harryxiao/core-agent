# Proposal 0266 — 后台进程跨重启登记

## Why

`ProcessRegistry` 目前只存在于内存：core-agent 进程退出（或 CLI 重启）后，先前
`background=true` 启动的任务仍在运行（`start_new_session` 使其脱离父进程），但
`tools.process` 的 `list` / `status` / `output` 一律查不到 —— 日志文件还在磁盘上，模型却
失去定位它们的唯一入口（pid 与输出路径）。长任务跨会话时需要重新 `ps` 翻找，且无法确认某个
pid 是否仍是当初那个进程。

## What Changes

- **登记项持久化**：注册表把任务元数据（pid、输出路径、启动时间、运行类型、进程启动标识）
  原子写入 `$CORE_STATE_DIR/processes.json`（0600）；添加任务时落盘；**不**记录脚本正文 /
  命令 / 环境变量。
- **启动时恢复**：`ProcessRegistry` 构造时加载登记项为「恢复项」（无 `Popen` 句柄），
  `tools.process list/status/output` 继续可用；`info()` 增 `restored` 标记。
- **存活与身份核对**：恢复项以 `os.kill(pid, 0)` 判存活；Linux 上再与
  `/proc/<pid>/stat` 的 starttime 比对，PID 复用（starttime 不符）视为已退出，不误报运行中。
- **恢复项拒绝终止**：无进程句柄、身份无法在全部平台安全验证 ⇒ `tools.process_kill` 对恢复项
  返回 `killed=false`（`restored=true`），实际不触达进程；终止能力仍仅限本进程启动的任务。
- **失败降级**：持久化 / 加载为观测辅助，读写失败 SHALL NOT 阻止后台任务启动或注册表使用；
  损坏文件按空注册表处理。

## Impact

- `src/core/tools/execution.py`（`ManagedJob` / `ProcessRegistry` / 状态目录助手）、
  `src/core/tools/builtin.py`（`_kill_job` 恢复项分支）。
- 规格：`tool-use` **MODIFIED**「后台命令执行与进程管理」。
- 测试：新增 `tests/test_process_persistence.py`；既有 `tests/test_process_execution.py` 保持。
- 文档：`doc/02-modules/tool-use.md`、`doc/03-interfaces/tool-use-interface.md`、
  `doc/04-testing/test-cases.md`、ADR / 台账。

## 不做（明确边界）

- 不做跨重启终止：恢复项只读（巡检 / 日志），因为非 Linux 平台无法核对进程身份，PID 复用时
  终止可能误杀无关进程。
- 不做孤儿任务自动回收、不接管父进程死亡后的进程树、不做流式输出。
- 不持久化命令 / 脚本正文 / 环境变量；不记录退出码历史（恢复项退出码未知）。
- 不引入第三方依赖；持久化失败不重试、不告警（无日志设施，保持静默降级）。
