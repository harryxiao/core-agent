# Tasks 0259 — 命令执行进程治理与后台任务

## 1. 规格

- [x] 1.1 `tool-use` delta：MODIFIED「超时与资源上限」；ADDED「后台命令执行与进程管理」。
- [x] 1.2 `permission` delta：MODIFIED「分级权限体系」（`process` 只读词元）。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_process_execution.py`：
      - 前景超时杀整棵进程树（孙进程延迟写文件探针）
      - `CancelledError` 也杀树
      - 脚本超时经 provider 返回 `TIMEOUT`
      - 后台返回 pid/日志路径、日志 0600、`tools.process` list/status/output
      - `tools.process_kill` 需审批；kill 后进程退出；未知 pid 返回 `found=False`
      - 注册表上界；`timeout` 越界 / NaN 拒绝
      - Windows 分支 mock：`creationflags`、无 `start_new_session`、`taskkill /T /F`
- [x] 2.2 `tests/test_permission.py`：`tools.process` = READ；`tools.process_kill` = HIGH_RISK。
- [x] 2.3 适配：`test_tool_use.py`、`test_os_aware_shell.py`、`test_windows_run_completeness.py`
      改 patch `core.tools.execution`；`test_code_run_timeout_structured` 断言 `TIMEOUT`。

## 3. 实现

- [x] 3.1 `tools/execution.py`：seam、进程树终止、注册表、后台 spawn、日志目录。
- [x] 3.2 `builtin.py`：`code_run` 前景/后台；`tools.process` / `tools.process_kill`；
      `builtin_tools()` 共享一个注册表。
- [x] 3.3 `runtime.py`：注册 `process:read` / `process:write`。
- [x] 3.4 `permission/policy.py`：`process` 加入 `_READ_TOKENS`。

## 4. 验证

- [x] 4.1 探针：逐点摘除 ⇒ 对应用例红；复原 md5 一致。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0249；`coding-plan/known-risk.md` E195 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §171；模块 / 接口文档补写。
- [x] 5.3 单次提交 `feat(tool-use): ... change 0259 / ADR-0249 / 台账 E195`；更新记忆。
