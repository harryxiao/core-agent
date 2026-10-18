# Design 0259 — 命令执行进程治理与后台任务

## D1 执行 seam：`tools/execution.py`

L1 模块（仅 stdlib，不 import runtime / memory），集中承载进程生命周期：

- `_IS_WINDOWS = sys.platform == "win32"`（可 monkeypatch 的模块常量）。
- `_create_subprocess_exec = asyncio.create_subprocess_exec`（测试 seam）。
- `run_foreground(cmd, timeout, cwd, env)`：独立进程组启动；`asyncio.wait_for(proc.communicate(),
  timeout)`；`TimeoutError` / `CancelledError` 先 `terminate_tree` 再 `wait`，超时重抛
  `TimeoutError` 让 `ToolProvider` 归一为 `TIMEOUT`。
- `terminate_tree(pid)`：POSIX `os.killpg(os.getpgid(pid), SIGKILL)`，失败回退 `proc.kill()`；
  Windows `taskkill /PID <pid> /T /F`；吞 `ProcessLookupError` / `PermissionError`。
- `spawn_background(cmd, cwd, env, output_path)`：`subprocess.Popen(stdout=fh, stderr=STDOUT,
  start_new_session=True)`，父进程立即关闭句柄；返回 `ManagedJob`。
- `ProcessRegistry`：`RLock` 保护，`max_jobs=32`；插入前先清 `poll() != None` 的已退出项，
  全在运行则拒绝新任务（不杀活进程腾位）。**不存脚本正文**（避免敏感内容驻留）。
- `state_run_dir()`：`CORE_STATE_DIR`（缺省 `~/.core/state`）/`run`，目录 0700；日志用
  `os.open(O_CREAT|O_EXCL|O_WRONLY, 0o600)`。

测试统一 patch `core.tools.execution.*`，不直接改全局 `asyncio`。

## D2 前景：进程组与结构化超时

- POSIX `start_new_session=True` 让 child 成为新会话 / 进程组组长，`killpg` 覆盖全部后代。
- Windows `CREATE_NEW_PROCESS_GROUP` 只建组；终止用 `taskkill /T` 递归杀树。
- `timeout` 在 handler 校验：`math.isfinite` 且 `0 < timeout <= 600`；缺省 120。非法值抛
  `ValueError`（`Validator` 只校验类型，忽略 minimum/maximum）。
- 工具外层 `timeout_s=660` > 内层硬上限，外层兜底不会先触发；若仍取消，handler 的
  `CancelledError` 分支同样杀树。

## D3 后台：日志文件与注册表

- 只允许系统生成路径，**不接受**模型指定 `output_path`（否则可借截断写任意文件）。
- 返回 `{type, background: true, pid, output_path, started_at}`；`timeout` 对后台不适用。
- 后台任务不随 loop 结束强杀；生命周期由 `tools.process_kill` 显式管理。进程退出后注册表项
  保留（可查 exit code / 读日志），直到被新任务淘汰。

## D4 进程管理工具：拆两个

`ToolDef` 只有工具级 `reversible`，单工具 `action=kill` 无法做到「status 自动放行、kill 必审批」：

- `tools.process`（`list|status|output`）：`reversible=True`，coeffect `process:read`；
  `output` 仅读注册表内 pid 的日志尾部（缺省 8K、上限 64K）。
- `tools.process_kill`：`reversible=False`，coeffect `process:write` ⇒ `SafetyGate` 确认；
  权限引擎按 `kill` 词元判 `high-risk` ⇒ 双层保护。

`ProcessRegistry` 由 `builtin_tools()` 创建一次并注入 `code_run` 与两个进程工具；不同
`builtin_tools()` 调用（主子 Agent / 神兽）各自独立注册表，只能管理自己启动的任务。

## D5 权限分级

`PolicyEngine.classify("tools.process", ...)` 的词元含 `process`；当前 `_READ_TOKENS` 不含它，
会落 deny-by-default `HIGH_RISK`。把 `process` 加入只读词元，`tools.process` 判 `read`；
`process_kill` 先命中 `_HIGH_RISK_TOKENS` 的 `kill`，仍判 `high-risk`。

## 兼容性与回归面

- `type` / `cwd` / UTF-8 解码 / PowerShell 前导 / 确认门：语义不变。
- `timeout` 缺省 10→120、脚本超时 `EXECUTION_FAILED`→`TIMEOUT`：缺陷修复，规格与测试同步。
- `builtin_tools()` 由五件变七件；诊断计数随之变化（无精确值断言）。
- 后台能力缺省关闭（`background=False`），前景行为除超时参数外不变。

## 局限（登记）

1. 后台注册表仅进程内，重启后无法接管旧任务；日志文件不自动清理。
2. Windows 终止依赖系统 `taskkill`；不可用时回退 `proc.kill()`（仅直接子进程）。
3. 超时返回不携带部分 stdout/stderr（需要完整输出请用后台日志）。
4. `tools.process output` 可能把日志中的敏感文本回灌模型；与前景 stdout 同口径，写记忆前仍经
   `redact_secrets`。
