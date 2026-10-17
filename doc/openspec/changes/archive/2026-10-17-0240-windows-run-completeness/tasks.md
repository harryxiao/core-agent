# Tasks 0240

## 1. 规格
- [x] 1.1 `specs/loop/spec.md`：MODIFIED「运行环境事实」＋ 3 Scenario
- [x] 1.2 `specs/tool-use/spec.md`：MODIFIED「内置原子工具」＋ 2 Scenario
- [x] 1.3 `specs/ui/spec.md`：MODIFIED「code_run 活动标题按方言命名」＋ 1 Scenario

## 2. 测试（先红）
- [x] 2.1 `tests/test_windows_run_completeness.py`：环境块（可用 shell / 版本标签 /
      缺省缺失建议 python / 未知 OS / 全新进程 / cwd / 回退边界）
- [x] 2.2 同文件：`code_run` subprocess kwargs（UTF-8 解码 / python env / powershell preamble /
      `cwd` `~` 展开）
- [x] 2.3 同文件：TUI 有效 type 标题（powershell / bash / 事实不可得 → Shell）
- [x] 2.4 `tests/test_os_aware_shell.py`：既有「缺省=Bash」断言改为中性 `Shell`
- [x] 2.5 `frontend/src/lib/activity.test.js`：`code_run` 三档 + 缺省 `Shell` + 符号

## 3. 实现
- [x] 3.1 `env_shell.py`：`format_env_block` 增可用性 / 标签 / 缺省缺失 / 进程语义 / 回退边界；
      未知 OS 分支纠正
- [x] 3.2 `builtin.py`：UTF-8 解码、PowerShell preamble、`PYTHONIOENCODING`、`cwd` `~` 展开、
      schema / description
- [x] 3.3 `runtime.py`：`Runtime.env_snapshot` 字段并传入
- [x] 3.4 `ui/api.py`：可选 `env_snapshot` + `default_shell`
- [x] 3.5 `ui/repl.py`：`_code_run_name` / `_tool_name` / `format_action_event` 有效 type；
      TUI 与子任务调用点接线
- [x] 3.6 `entry.py`：`_build_ui` 注入快照；`_stream` 传 `default_shell`
- [x] 3.7 `frontend/src/lib/activity.js` + `Chat.svelte`

## 4. 文档
- [x] 4.1 `doc/03-interfaces/prompts.md`：动态块表补「运行环境」块
- [x] 4.2 `doc/03-interfaces/tool-use-interface.md`：`code_run` 的 `cwd` 展开与 type 优先
- [x] 4.3 ADR-0228（含 ADR-0227 D5 纠偏）

## 5. 收口
- [x] 5.1 四门禁：ruff check / ruff format --check / pyright（无参）/ pytest
- [x] 5.2 `openspec validate --all`
- [x] 5.3 归档（`/tmp/openspec_archive.py`，断言 0 Requirement / 0 Scenario 丢失）
- [x] 5.4 台账 `known-risk.md` E175、`test-cases.md` §151
- [x] 5.5 单次提交（含 `Co-Authored-By`）
