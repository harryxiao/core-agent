# Proposal 0272 — 工具参数按需注入（Claude Code 对齐建议 5b / 账本 E91）

## Why

主工具面已从「内置五件」增长到十五件以上：内置原子工具（含 `tools.process` /
`tools.process_kill`）、`tools.gate_run`、`tools.context_read`、`tools.delegate`、
`tools.install` / `tools.uninstall` / `tools.list`、`tools.tasks`，加上 MCP 端点动态注册的
`mcp.<端点>.<工具>`。每一轮推理请求都把**全部**工具的完整参数 schema 随请求发送，而单轮
通常只用其中两三个——工具 schema 是每轮固定成本，工具越多、每轮越贵，且挤占上下文预算。

Claude Code 的做法是「工具描述常驻、参数按需加载」：系统提示里始终可见工具清单，模型在
真正调用前先查参数。本 change 对齐该形态：**工具目录不收窄，只把参数 schema 收窄到核心集 +
本回合已加载集**，模型经 `tools.schema_read` 按需加载；`all` 作为 kill-switch 保留旧行为。

## What Changes

- 新配置项 `loop.tool_scope`（CLI `--loop.tool-scope` / env `CORE_LOOP_TOOL_SCOPE` /
  yaml `loop.tool_scope`）：取值 `all` | `auto`，**缺省 `auto`**；非法取值**校验期阻断启动**。
- `LLMPlanner` 增 `tool_scope` 构造参数（**构造缺省 `all`**，保证直接构造 planner 的既有
  调用逐字不变）；只有组合根的主 planner 注入配置值。
- `auto` 生效条件：已注册工具数 **> 8** 且 `tools.schema_read` 已注册。此时请求只携带
  **核心工具集**（`file_read`/`file_write`/`file_patch`/`code_run`/`web_fetch`/
  `context_read`/`delegate`）、**本回合已加载工具**与 `tools.schema_read`。
- 新工具 `tools.schema_read`（只读、可逆、coeffect `schema:read`）：不带参数列出全部可用
  工具；带 `tool_ids` 返回其描述与参数 schema，未知 id 记入 `unknown` 不阻断。
- 循环在 `tools.schema_read` 成功后把请求的已注册 id 吸收进本轮上下文包的
  `loaded_tools`，**下一轮**请求即携带其 schema；集合随回合结束清空。
- 系统提示的「可用工具」目录（id + 描述）**不收窄**；`auto` 生效时追加一行说明
  「未注入 schema 的工具先经 tools.schema_read 加载参数」。

## Impact

- 代码：`src/core/loop/{planner.py,protocol.py,default.py}`、
  `src/core/tools/builtin.py`、`src/core/runtime.py`、`src/core/configuration/manager.py`。
- 测试：新增 `tests/test_tool_scope.py`；必要时补既有 planner / runtime 断言。
- 规格：`loop` ADDED「工具参数按需注入」；`configuration` ADDED「工具注入范围配置」；
  `tool-use` ADDED「工具参数查询」。
- 兼容：`loop.tool_scope=all` ⇒ 请求与引入前**逐字一致**；子 Agent / 神兽 / 宠物工具面
  ≤ 8 件且不注入该开关 ⇒ 行为不变。约束工具数上限的阈值（8）是**小工具面免加载**的兜底，
  避免自建 planner 因未注册 `schema_read` 而出现不可达工具面（此时回落全量注入）。

## 不做（明确边界）

- 不改工具注册面：`ToolProvider.active_tools()` 仍是全量真源；权限、coeffect 校验、
  撤销与去重都看全量集合。`auto` **只影响请求侧 schema 注入**，不是访问控制。
- 不做懒注册 / 懒连接：MCP 工具照旧装配期连接；`auto` 只省参数 schema 的每轮 token。
- 不改变子 Agent / 神兽 / 宠物的工具集与 planner 参数（构造缺省 `all`，工具数 ≤ 8 时
  threshold 也全量注入）。
- 不跨回合记忆已加载集合（新回合从核心集重新开始）；不做按需自动推断相关工具。
- 不引入第三方依赖、不改 `exclude_source_prefixes`。
