# Proposal — 计划轮可信度与可打断性（0316）

## Why

用户实测（2026-10-24，TUI `/plan` 模式，目标「在 arxiv.org 查询 Agent RSI 相关论文」）暴露三处缺陷：

1. **工具面误判**：勘察轮回复「运行时未安装任何插件（tools.list 返回空），因此没有可用的
   网络查询/搜索原子工具……建议安装 arxiv-mcp-server」。事实相反 —— 内置 `tools.web_fetch`
   始终在工具面（批准后的自跑轮确以 `tools.web_fetch` 访问 arxiv.org）。根因：`tools.list`
   只返回 `{"installed": [...]}`（**插件安装面**），描述与载荷都没说明「内置原子工具不受
   插件安装状态影响」，模型把插件清单当成了工具全集。
2. **等待期不可见、不可打断**：勘察结束后进入拆解，状态行仍停在「只读勘察中」（拆解为
   阻塞式 LLM 调用，实测 27s，最坏到重试预算），期间输入被忙态拒绝；草案挂起后输入面只认
   y/n；`Ctrl+B` 只打印 TTS barge-in 提示、**不打断本轮** —— 与 `ui` 规格
   「Ctrl+B 打断（停本轮）」不符，用户失去唯一逃生通道（观感即「卡住、无法再输入」）。
3. **回落计划污染目标**：checkpoint 证据显示被批准的计划只有 1 个子任务，其目标**逐字等于**
   「原始目标 + 『只读勘察结论（供拆解参考）』 + 勘察原文」——拆解器回落（`_fallback`）把
   勘察结论变成了子任务指令，批准后主 Agent 按「无法执行…建议安装插件」这段文字执行。
   `draft_plan` 只还原了顶层 `goal`，未归一子任务目标；0313 的退化守卫只覆盖重拆路径。

## What Changes

- **A. `tools.list` 明示范围**：工具描述与返回载荷附注「本清单只含经安装面安装的插件；内置
  原子工具与插件安装状态无关、始终按工具面可用」。
- **B. 草案归一拆解器回落**：`TaskScheduler.draft_plan` 在单子任务且其目标逐字等于送入拆解
  文本时，把该子任务目标还原为**原始目标**（勘察上下文 SHALL NOT 成为子任务指令）；其余
  拆解结果逐字保留。
- **C. 拆解阶段可见**：`UIAPILayer.run_plan_turn` 在拆解前产出 `plan.drafting` 阶段事件，
  TUI 状态行由「只读勘察中」切到「拆解计划中」。
- **D. `Ctrl+B` 真正打断本轮**：取消在途轮次 worker（轮次收尾复位忙态、输入恢复、进程不
  退出）；计划草案 y/n 待决时等价于放弃（草案丢弃、模式回 `quick`）；无在途轮次时保持既有
  barge-in（TTS）语义。

## Impact

- 规格：`tool-use` MODIFIED ×1；`orchestration` MODIFIED ×1；`ui` MODIFIED ×2。
- 代码：`src/core/tools/install_tools.py`、`src/core/orchestration/scheduler.py`、
  `src/core/ui/api.py`、`src/core/ui/repl.py`。
- 行为：未装插件、未用 `/plan` 的路径逐字不变；**零新配置键**、零新依赖、零新增状态文件。

## Out of Scope（明确不做）

- **不改勘察轮 prompt / 工具面**：`tools.web_fetch` 本就可用，缺陷在 `tools.list` 的口径。
- **不改 `LLMSubtaskPlanner` 回落策略**：执行路径的既有回落语义不变，只在草案入口归一。
- **不引入 arxiv / MCP 专用插件**，不做「提示即安装」的自动动作。
- **不改 `/exit` 与 Ctrl+Q 语义**（0315 已收口）。
