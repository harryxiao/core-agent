# Design 0288 — 台账销账与 E100 盘点

## D1 E55 直接销账，不做新实现

E55 的原始描述是「主 loop 单工具协议只取首个 `tool_call`」。change `0257` 已从三层改掉：

1. `LLMPlanner._from_tool_calls`（`src/core/loop/planner.py:855-871`）按 provider `index`
   **全量**映射；单调用仍返回 `Action`，多调用返回 `ActionGroup`。
2. `DefaultLoop`（`src/core/loop/default.py:601`）把 `ActionGroup` 展开为多个动作，逐个进入
   既有执行体；不是只执行首个。
3. `tests/test_parallel_tool_calls.py` 锁定 planner（非流式/流式）、loop 执行顺序、重复调用
   抑制（批内 + 轮内紧邻）。

因此 E55 无剩余实现面，销账即可。保留原始来源 `phase-34.md:65` 供追溯。

## D2 E100 的「未注册」不等于「待实现」

把 11 个动词按**真实承载**分为两类，而不是一律按「补注册」处理：

| 类 | 动词 | 依据 |
|---|---|---|
| 已有真实承载（6） | `version` / `help` / `install` / `uninstall` / `list` / `permission-mode` | `--version`；`-h/--help`；`plugin install|uninstall|list`（`skill` / `mcp` 有域内变体）；`config get|set permission.mode` |
| 无真实后端（5） | `kill` / `logs` / `info` / `auth` / `gateway` | lifecycle 全组是 MVP 桩；无日志读取源；无资产详情；无认证子系统；`gateway()` 是桩，`serve` 才是真实 Web 入口 |

只有第一类可以「不新增子命令」地满足用户可达性；第二类若照旧口径注册，会得到一组**永远
成功但什么也不做**的命令，比不注册更糟（用户会误判能力存在）。因此本轮拒绝「全注册」，
把解挂条件写明。

## D3 守卫钉住「差集」，不解析语义

`cli_ops/dispatcher.py` 的六组集合是**接口层清单**；argparse 顶层子命令是**用户可达清单**。
E100 的定义就是两者之差。守卫：

- `actual = (_LIFECYCLE | _STATUS | _ASSET | _SECURITY | {"mcp", "gateway"}) - parser_choices`
- `documented = `cli-ops-interface.md` 中唯一一行「未注册动词（守卫）」里、破折号前的反引号动词`
- 断言两者集合相等且声明的计数一致。

`mcp` 按 `_group_of("mcp")` 的语义计入顶层；`add/remove/list` 是 `mcp` 的子动作，不计入。
守卫不检查「映射面是否仍然正确」——那需要逐命令运行，超出文档守卫的成本/收益。

## D4 不删除不可达分支

`CLICommandDispatcher.status()` 在 change `0162` 后不可从 CLI 触达（`status` / `doctor`
改走 `core/diagnostics`），但仍是六组模型的一部分；删除它会影响 `cli_ops` 的接口测试与
`CommandGroup.STATUS` 的完整性。本轮明确「不改不删」，销毁性清理另立 change。

## 局限

- 守卫只锁动词集合与计数，不锁每个动词的映射说明是否过时。
- `version` / `help` 是全局 flag，不是子命令；盘点把它们归为「已有真实承载」而非「已注册」，
  因此仍计入未注册差集。
- 第二类 5 个动词的「无后端」判断基于当前代码快照（2026-10-18）；后端落地前不注册。
- 文档不回显任何密钥、任务正文或用户路径。
