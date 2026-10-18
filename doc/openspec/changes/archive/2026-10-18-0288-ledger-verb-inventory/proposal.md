# 0288 — 台账销账：E55 多工具调用已闭 ＋ E100 CLI 动词盘点

## Why

`coding-plan/known-risk.md` §1 有两条与代码现状不符的挂账：

- **E55（主 loop 丢弃多余 `tool_call`）**：该描述停留在 change `0257` 之前。现状
  `planner.py::_from_tool_calls` 已把**全部**原生 `tool_calls` 映射为 `ActionGroup`，
  `default.py:601` 逐个展开执行，`tests/test_parallel_tool_calls.py` 三层锁定
  （planner 全量映射 / loop 按序执行 / 重复调用抑制）。账未销，导致后续盘点反复把它
  当开放缺口重报。
- **E100（运维动词未注册为子命令）**：change `0162` 只闭了 `status` / `doctor`，剩余
  11 个动词（`kill` / `logs` / `version` / `help` / `install` / `uninstall` / `list` /
  `info` / `auth` / `permission-mode` / `gateway`）一直沿用「逐动词补 argparse 注册面」
  的开工口径。但**逐项核对后发现其中多数已有真实承载面**（`--version` / `-h` /
  `plugin ...` / `config get|set permission.mode`），其余 5 个背后仍是 dispatcher 的
  MVP 桩或根本没有后端。直接「全注册」只会扩大空操作面，不是收口。

本轮只做**盘点和销账**：把两条账与代码对齐，并加一条守卫防止 E100 清单再次漂移。

## What Changes

- **E55 销账**：`known-risk.md` E55 行改为**已闭**，证据锚定 change `0257` / ADR-0248 /
  §170 与 `planner.py:855-871` / `default.py:601` / `test_parallel_tool_calls.py`。
- **E100 盘点**：
  - `doc/03-interfaces/cli-ops-interface.md` §5 的「未注册动词」一条改为**盘点口径**：
    - **已有真实承载（不新增子命令，6 个）**：`version` → `--version`；`help` → `-h/--help`；
      `install` / `uninstall` / `list` → `plugin install|uninstall|list`；`permission-mode` →
      `config get|set permission.mode`。
    - **无真实后端（保持未注册，5 个）**：`kill`（lifecycle 全组是 MVP 桩）、`logs`（无日志
      读取源）、`info`（无资产详情面）、`auth`（无认证子系统）、`gateway`（`serve` 才是真实
      Web 入口，`dispatcher.gateway()` 是桩）。
  - 新增一行机读「未注册动词（守卫）」＋ `tests/test_cli_verb_inventory.py`：解析该行，
    与 `cli_ops/dispatcher.py` 六组动词集合减去 argparse 顶层子命令集合的差集逐项比对。
    今后注册/新增动词而忘同步文档即转红。
- **台账与索引**：ADR-0278；`known-risk.md` §3 ADR-0278 局限行；`doc/04-testing/test-cases.md`
  §200（TC-CLI-VERB-INV）。

## Non-goals

- **不新增任何 argparse 子命令**，不改 `entry._HANDLERS`，不改 `CLICommandDispatcher` 行为。
- 不实现 `kill` / `logs` / `info` / `auth` / `gateway` 的真实后端；它们的解挂须在后端落地后
  另立 change。
- 不删除 `cli_ops/dispatcher.py` 的不可达 `status()` 分支（销毁性清理另立 change）。
- 不改 `phase-34.md` 等历史记录里的原始缺口描述。
- 无规格 delta（`skip_specs: true`），无运行时代码行为变化。

## Impact

- 代码：无（仅新增测试）。
- 文档：`doc/03-interfaces/cli-ops-interface.md`、`coding-plan/known-risk.md`、
  `doc/01-architecture/adr.md`、`doc/04-testing/test-cases.md`。
- 测试：新增 `tests/test_cli_verb_inventory.py`（2 例）。

## Risks

- 守卫只锁**动词集合**，不锁每个动词的语义映射是否仍然成立（如 `plugin list` 未来改名）。
  缓解：映射说明在 §5 明写「落地面前提」，改面时需同步。
- argparse 顶层子命令通过私有 `parser._subparsers` 读取；CPython 的 argparse 结构多年稳定，
  若将来变化，失败信息会直接指出差集。
- `mcp` 在 dispatcher 中按**顶层命令**归组（`connection`），其子动作 `add/remove/list` 不是
  顶层动词；守卫按 `_group_of` 的语义只把 `mcp` 计入。
