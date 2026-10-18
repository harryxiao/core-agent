# Proposal 0259 — 命令执行进程治理与后台任务

## Why

对比审查（2026-10-18）确认 `tools.code_run` 的超时语义与长命令能力存在两层缺陷：

1. **超时只取消等待，不终止进程**：handler 用 `asyncio.to_thread(subprocess.run, timeout=...)`，
   `ToolProvider.ainvoke` 的外层 `asyncio.wait_for(timeout_s=60)` 只取消协程，工作线程与子进程继续
   运行；`subprocess.run` 的内层超时只杀直接子进程，**孙进程可逃逸**。上层收到 `TIMEOUT` 时命令
   仍可能在写文件。脚本层超时还被归为 `EXECUTION_FAILED`，与规格「超时 ⇒ 终止并返回超时错误」
   不一致。
2. **长命令不可用**：脚本超时缺省 10s、工具外层超时 60s，编译 / 测试 / 构建常被截断；没有后台
   执行，模型只能反复轮询短命令。接口文档长期列有 `tools.process`，但代码中**不存在**该工具。

## What Changes

- 新增 `src/core/tools/execution.py`：前景执行改用 `asyncio.create_subprocess_exec`，以独立进程组
  启动；超时 / 取消时终止**整棵进程树**并返回结构化 `TIMEOUT`。POSIX 用 `killpg`，Windows 用
  `taskkill /T /F`。
- `tools.code_run` 增加 `background`：后台任务立即返回 `pid` 与输出文件路径
  （`$CORE_STATE_DIR/run/<uuid>.log`，0600）；脚本超时缺省 120s、硬上限 600s，工具外层 660s。
- 新增只读工具 `tools.process`（`list` / `status` / `output`）与不可逆工具 `tools.process_kill`；
  仅管理本进程启动的后台任务，注册表有界（32）。`tools.process` 在权限分级中判 `read`，
  `process_kill` 因 `kill` 词元仍判 `high-risk`。
- 注册 `process:read` / `process:write` coeffect。

## Impact

- `src/core/tools/execution.py`（新）、`builtin.py`、`runtime.py`、`permission/policy.py`。
- 规格：`tool-use` **MODIFIED** 1 req（超时语义）+ **ADDED** 1 req（后台与进程管理）；
  `permission` **MODIFIED** 1 req（`process` 为只读词元）。
- 测试：`tests/test_process_execution.py`（新）；`test_tool_use.py`、`test_os_aware_shell.py`、
  `test_windows_run_completeness.py`、`test_permission.py` 适配新执行 seam。
- 兼容性：`type` / `cwd` / 编码 / 确认门语义不变；`timeout` 缺省值与错误码变化属本次修复。

## 不做（明确边界）

- 不管理任意 PID（仅注册表内后台任务）；不做流式 / PTY 实时输出。
- 不做孤儿后台进程自动回收或跨重启 pid 恢复；日志文件不自动清理（已知局限）。
- 不改变 `web_fetch` 的字节截断语义。
