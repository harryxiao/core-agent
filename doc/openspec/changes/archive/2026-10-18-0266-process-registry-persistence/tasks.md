# Tasks 0266 — 后台进程跨重启登记

## 1. 规格

- [x] 1.1 `tool-use` delta：MODIFIED「后台命令执行与进程管理」（持久化 / 恢复 / 身份核对 /
      恢复项拒绝终止）。

## 2. 红测试（先写）

- [x] 2.1 注册表落盘 `processes.json`：0600、原子替换无残留临时文件、只含元数据键。
- [x] 2.2 新注册表恢复登记项：`list` / `status` / `output` 可用，`restored=true`，运行中判定正确。
- [x] 2.3 已退出 pid 的恢复项 `running=false`。
- [x] 2.4 Linux 身份核对：starttime 匹配 ⇒ 运行中；不匹配（PID 复用）⇒ 已退出。
- [x] 2.5 恢复项 `process_kill` 返回 `killed=false` / `restored=true`，进程仍存活。
- [x] 2.6 损坏文件 / 非法条目容忍；超过 `max_jobs` 时保留最新条目。
- [x] 2.7 持久化失败不阻止后台任务启动与登记。

## 3. 实现

- [x] 3.1 `execution.state_dir()`；`ProcessRegistry` 加载 / 原子保存 / 上界。
- [x] 3.2 `ManagedJob.proc` 可为 `None`、新增 `start_ticks`；`is_running()` / `info()` 恢复分支。
- [x] 3.3 `_pid_alive` / `_start_ticks` / `_identity_ok`。
- [x] 3.4 `builtin._kill_job` 恢复项拒绝终止分支。

## 4. 验证

- [x] 4.1 反证：摘恢复加载 / 摘身份核对 / 摘恢复项拒绝终止 / 摘原子替换 ⇒ 对应用例红；
      复原 `md5sum` 同。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR；`coding-plan/known-risk.md` 台账条目。
- [x] 5.2 `doc/04-testing/test-cases.md`；`doc/02-modules/tool-use.md`、
      `doc/03-interfaces/tool-use-interface.md`。
- [x] 5.3 单次提交 `feat(tooling): ... change 0266 / ADR-NNNN / 台账 ENNN`；更新记忆。
