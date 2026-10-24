# Design — 计划轮延迟与勘察工具面保真（0317）

## 证据

| # | 观察 | 数值 / 来源 |
|---|---|---|
| E1 | 计划勘察轮 17 轮、约 180s，工具调用几乎全部 `INVALID_ARGS`（0ms） | trace `ebcfabbf`，12:16:32→12:19:32 |
| E2 | 勘察期 `tools.schema_read(["tools.web_fetch"])` **成功返回 schema**，但随后 `tools.web_fetch` 调用返回未知工具 | trace 12:16:50 / 12:16:53 |
| E3 | 计划视图按 `PolicyEngine` 只含 `READ`：`web_fetch` / `code_run` / `delegate` 均判 `high-risk` | `readonly_tool_ids` 实测输出 `['file_read','schema_read','tasks', …]` |
| E4 | 子集视图复用同一 `Tool` 实例，`schema_read` 的 `catalog` 闭包仍指向根 provider | 4 行脚本复现：视图内 `schema_read("tools.web_fetch")` 返回完整 schema |
| E5 | 用真实勘察文本重放 `decompose`：一次 **60.1s 超时**并回落单子任务（`subtasks=1, criteria=0`） | `uv run python` 重放 |
| E6 | 同一请求加 `max_tokens`：2000→**9.7s**、4000→**7.4s**、8192→**13.0s**，输出正常 | 同上 |
| E7 | 拆解使用主 provider：`timeout=60`、`max_retries=3` ⇒ 最坏 `60×4 + 1+2+4 ≈ 247s` | `runtime.py:1771` + `configuration/models.py` 缺省 |

## 决策

### D1 计划视图的 `schema_read` 目录绑定视图自身（修复）

`ToolProvider.subset()` 返回的视图复制了 `Tool` 实例；`schema_read(catalog=tools.active_tools)`
的闭包捕获的是**根** provider。组合根新增 `_plan_tool_view(tools)`：先 `subset(readonly_ids)`，
再 `unregister(SCHEMA_READ_TOOL_ID)` + `register(schema_read(catalog=view.active_tools))`。

- 只在组合根做，**不**修改 `ToolProvider.subset` 的通用语义（子 Agent / 宠物等其它视图不因此
  获得新行为），也避免 `tools/provider.py` 反向依赖 `builtin`。
- 结果：勘察期 `schema_read` 无参列表只列视图内工具；请求视图外 id ⇒ `unknown`，模型一轮即知
  不可用，不再空转。
- **被拒**：① 在 `subset` 内自动重绑（provider 层要 import 具体内置工具，层次倒置）；
  ② 只在提示词里写「不要调用网络工具」（模型仍可从 schema_read 拿到 schema，治标不治本）。

### D2 拆解 / 验收请求带输出上界（修复）

`LLMSubtaskPlanner` 与 `LLMVerifier` 增加可选 `max_tokens`（`None` ⇒ 不写字段，既有直接构造
的调用方逐字不变）；组合根注入 `config.output_reserve()`（与主 `LLMPlanner` **同一源**）。

- 拆解输出是 ≤6 个子任务的 JSON，8192 上界充足；实测 13s 内完成。
- 上界把「无界生成长尾」变成端点上界，配合 D3 的墙钟构成双层护栏。
- **被拒**：① 给拆解单独新增配置键（与 `loop.output_reserve` 语义重复，违反「零新配置键」）；
  ② 只调小 `max_retries`（全局影响主循环与工具面，放大面不可归因）。

### D3 计划拆解等待有界（新增护栏）

`UIAPILayer.run_plan_turn` 在 `plan.drafting` 之后用 `asyncio.wait_for` 包住
`orchestrator.draft_plan(...)`：

- 上限 = `llm.timeout + 30s`（无 LLM 配置时 90s）；可经构造参数 `plan_draft_timeout` 覆盖
  （仅测试 / 嵌入式装配使用，生产不传）。
- 超时 ⇒ `UI_PLAN_DRAFT_FAILED`，文案含上限与「请重试或改用 /quick」；草案不创建、模式保持
  `plan`（与既有拆解失败语义一致）。
- **被拒**：① 超时静默回落单子任务（用户拿到劣质计划却不知情）；② 不设上限只靠 provider 重试
  （最坏 4 分钟无回执）；③ 新增 `ui.plan_draft_timeout` 配置键（交互路径的护栏，不是装配期参数）。

## 规格映射

- `tool-use` MODIFIED「工具参数查询」：受限视图目录不得泄漏视图外工具；新增 Scenario
  「受限视图不泄漏视图外工具」。
- `orchestration` ADDED「拆解与验收调用的输出上界」：LLM 拆解/验收请求 SHALL 在组合根注入输出
  上界时携带 `max_tokens`；未注入 SHALL 保持逐字不变。
- `ui` ADDED「计划拆解的等待上界」：拆解等待 SHALL 有界，超时 SHALL 返回
  `UI_PLAN_DRAFT_FAILED` 且不创建草案。

## 测试与反证

- 正证：`tests/test_plan_mode.py`（视图目录不泄漏、按 id 请求视图外工具落 `unknown`；拆解超时
  → 结构化错误且无草案）、`tests/test_orchestration.py`（拆解/验收请求携带 `max_tokens`；
  未注入时为 `None`）。
- 反证（`cp` 到 `/tmp` + 改坏 + 复原 + `md5sum`）：
  1. 去掉 `_plan_tool_view` 的目录重绑 ⇒ 泄漏用例红；
  2. 去掉 planner/verifier 的 `max_tokens` 透传 ⇒ 上界用例红；
  3. 去掉 `wait_for` ⇒ 超时用例红（3s 内无法收敛）。

## 局限

- 端点长尾本身不可控；D2/D3 只保证「有上界、有回执」，不保证拆解一次成功。
- 拆解超时后 provider 的在途线程不会被中断（`asyncio.to_thread` 不可取消），仍可能完成并丢弃。
- 视图重绑只覆盖 `schema_read`；若未来新增其它「目录型」只读工具，需同样绑定视图。
- 计划勘察仍无网络能力（产品取舍未变）。
