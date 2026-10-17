# Proposal 0257 — 并行工具调用、重复写抑制与原子写

## Why

会话 `cb37aba3ddf54bcc9336be2464c95c07` 复盘（P1）暴露三处工具执行层缺陷：

1. **原生并行 `tool_calls` 只执行首个**：`LLMPlanner._from_tool_calls` 明写「并行多调用取首个」，
   其余调用被**静默丢弃**。模型一次请求「写 A + 写 B」时只落 A，随后模型看到 A 成功却断言失败，
   在后续轮次重复发起写入 —— 这正是会话里「写入无效 / 重复 `file_write`」的直接来源。
2. **重复写无抑制**：同一批或紧邻轮次的完全相同写动作被反复执行（每次含效应快照与磁盘 I/O），
   放大副作用与 token 消耗。
3. **`tools.file_write` 非原子**：`open("w")` 先截断再写，进程中断 / 并发读会看到**空文件或半截
   内容**；写失败时原文件已被截断，无法回滚到「写前」的完整状态（撤销快照只在成功后才压栈）。

## What Changes

- **一次推理执行全部原生工具调用**：新增 `ActionGroup`（`loop.protocol`），planner 把一次响应里的
  全部合法 `tool_calls` 映射为动作组；loop 按 `index` 顺序逐个执行（各自走中间件 / 确认门 / 观测
  / 事件 / 压实阈值）。解析失败的批次整体按终止失败动作处理，**不部分执行**。
- **重复调用抑制**：① 同一批内完全相同的 `(tool_id, 规范 JSON 参数)` 只执行首个；② 同一轮内
  **紧邻重复**的写动作（`tools.file_write` 非 append、`tools.file_patch`）若上次已成功，跳过执行并
  复用上次结果。被抑制的调用仍产出正常 `action_started` / `action_completed`（`duration_ms=0`）并
  记 `action_deduplicated` 遥测，模型仍收到观测回灌。
- **`file_write` 原子覆盖**：覆盖模式先在**同目录**写临时文件、`flush` + `fsync`，再
  `os.replace` 原子替换；失败清理临时文件、目标文件**逐字不变**。追加模式（`a`）语义不变。
  撤销快照 / 逐次回滚语义不变。

## Impact

- `src/core/loop/protocol.py`：新增 `ActionGroup`。
- `src/core/loop/planner.py`：`_from_tool_calls` → 全量映射；单调用仍返回 `Action`（既有行为逐字不变）。
- `src/core/loop/default.py`：`_reason_events` 展开动作组；主循环支持待执行队列 + 重复写抑制。
- `src/core/tools/builtin.py`：`file_write` 覆盖模式原子化。
- 规格：`loop` **ADDED** 1 req / 4 scen；`tool-use` **ADDED** 1 req / 3 scen。
- 兼容性：单工具调用、文本回复、非流式路径与非写工具的事件序**逐字不变**；无新配置键。

## 不做（明确边界）

- 不做**真并行**执行（工具间无依赖分析；按 `index` 串行更可预测，且观测回灌顺序稳定）。
- 不做跨轮次、跨中间动作的重复抑制（仅同批 + **紧邻**重复；轮询类动作不得被误杀）。
- 不改变 append 模式（追加语义天然非幂等）。
- 不新增"批次失败"错误码：解析失败沿用 `LLM_PLAN_PARSE_FAILED` 终止动作。
