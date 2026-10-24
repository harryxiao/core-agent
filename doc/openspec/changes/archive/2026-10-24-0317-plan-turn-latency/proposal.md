# Proposal — 计划轮延迟与勘察工具面保真（0317）

## Why

用户实测：`/plan` 后「计划拆解耗时 150 秒都没有完成」。对照 trace 与离线重放，定位到两处独立缺陷：

1. **勘察轮空转约 3 分钟**（trace `ebcfabbf`，12:16:32→12:19:32，17 轮）。计划轮按规格只暴露
   `READ` 级工具视图（`web_fetch` / `code_run` / `delegate` 均为 `high-risk`，视图外），但
   `tools.schema_read` 的目录闭包绑定在**根工具面**上：勘察期它成功返回了 `tools.web_fetch`
   等视图外工具的 schema，模型据此连续调用 10 次，每次 0ms 得到 `INVALID_ARGS`（未知工具），
   一直到第 17 轮才放弃。
2. **拆解无输出上界、交互路径重试放大等待**。用上一轮真实勘察文本重放 `decompose`：一次
   60.1s 超时并回落单子任务；同一请求加 `max_tokens=2000/4000/8192` 后分别 9.7s / 7.4s /
   13.0s 正常产出。拆解走主 provider（`timeout=60s`、`max_retries=3`）⇒ 单次卡顿最坏被放大到
   `60×4 + 退避 ≈ 247s`，期间界面只有「拆解计划中」，无上限、无失败回执。

## What Changes

- **A（缺陷修复）** 计划只读视图的 `tools.schema_read` 目录绑定到**视图自身**：视图外工具
  SHALL 记入 `unknown`，SHALL NOT 返回其 schema。组合根抽出 `_plan_tool_view(tools)` 承载
  「子集 + 目录重绑」，勘察工具面与执行面回到同一真源。
- **B（缺陷修复）** `LLMSubtaskPlanner` / `LLMVerifier` 接受可选 `max_tokens` 并写入请求；
  组合根与主 planner **同源**注入 `config.output_reserve()`（缺省 8192）——拆解/验收输出从
  「无上界」收窄为端点上界，长尾生成不再拖满单次超时。
- **C（新增护栏）** 计划拆解的等待有界：`UIAPILayer` 对 `draft_plan` 施加墙钟上限（缺省
  `llm.timeout + 30s`；无 LLM 配置时 90s），超时返回 `UI_PLAN_DRAFT_FAILED` 并明示
  「请重试或改用 /quick」，SHALL NOT 无限等待或静默回落。

## Impact

- 代码：`src/core/runtime.py`（新增 `_plan_tool_view`）、`src/core/orchestration/planner.py`、
  `src/core/ui/api.py`。
- 测试：`tests/test_plan_mode.py`（视图目录不泄漏 / 拆解超时结构化）、
  `tests/test_orchestration.py`（拆解与验收请求携带输出上界）。
- 规格：`tool-use` MODIFIED ×1（工具参数查询：受限视图目录口径）；`orchestration` ADDED ×1
  （拆解与验收调用的输出上界）；`ui` ADDED ×1（计划拆解的等待上界）。
- **零新配置键、零新依赖**；缺省行为对「未配置 LLM 上限/未超时」的路径逐字不变（`max_tokens`
  仅在组合根显式注入时生效，`_plan_tool_view` 只作用于计划轮）。

## Out of Scope

- **不给计划勘察放行网络工具**：`web_fetch` 仍是 `high-risk`，勘察保持只读；检索仍落在批准后
  的执行（上一轮自跑已验证可正常检索）。
- 不改 provider 的重试策略（`llm.max_retries`）；不改 `llm.timeout` 缺省值。
- 不做拆解进度百分比 / 流式拆解；不治理端点本身的长尾。
- 不改 `tools.schema_read` 在主工具面的既有语义（含 MCP 动态工具）。
