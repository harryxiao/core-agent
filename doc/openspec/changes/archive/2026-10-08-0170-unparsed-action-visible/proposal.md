# 0170 · 未闭合动作载荷：识别面收紧 + 失败可见 + 原始产出可诊断

## Why

用户 2026-10-08 实测（原话）：「**json 指令当内容输出，还有问题**」—— 贴出的整轮输出里，
模型的动作 JSON 被**当成助手正文**渲染给用户（两坨 `{"tool_id": …}` 原文），且整轮**记为成功**。

trace 证据（`~/.core/state/traces.jsonl`，轮 `9ae2ae1fe3b34329a8cfaf028e722200`，reply 3386 字符）：

- 该轮 `loop_finished.reply` = 「清理状态确认：… 现在立提案 `fix-notes-turn-quality`，三件套落盘：」
  + **两个动作 JSON 原文**（`tools.code_run` 与 `tools.file_write`）；
- 该轮 `step_completed` × 2 **均 `failed=false`**、`loop_finished.failed=false` ⇒ **完全静默**；
- 量化：56 轮 `loop_finished` 中 **5 轮**（≈9%）reply 含 `"tool_id"`；这 5 轮的 **13 个
  `step_completed` 全是 `failed=false`**。

根因（逐字符复算）：

1. **尾部动作 JSON 被截断**：第二个动作（`tools.file_write`，`content` 3.4 KB）的**外层对象未闭合**
   —— 花括号配平**末态 `depth=1`**；但它的内层 `args` 对象恰好闭合，且**文本最后一个字符正是该
   `}`** ⇒ `_trailing_json_object`（只认「尾部最末一个能解析且其后无剩余」的对象）**返回了参数块**
   `{'path','content'}` 而非动作对象。
2. **兜底把原文当答复**：`planner._parse:314` 的 `embedded.get("tool_id")` 为假（拿到的是参数块）
   ⇒ 落 `Action(args={"reply": text})` ⇒ **整段（含两坨 JSON）成为最终回复**，`failed=False`、无留痕。

即 0166（ADR-0156）修好的是「尾部动作 JSON **合法**」那半边；「尾部动作 JSON **不合法/未闭合**」
那半边被明文留空（「宁可漏检不误判」），于是**同样的截断，只因为前缀了一段解释文字，就从
「失败可见」变成「静默成功 + JSON 当正文」**—— 非流式面 `{"tool_id": "tools.echo",` 本就落
`LLM_PLAN_PARSE_FAILED`（spec 既有 Scenario「解析失败使本轮失败」），加一行散文前缀就静默了。

**下游后果（两处，用户都踩到了）**：① JSON 原文进 `ctx.reply` ⇒ 进**转录**、进**记忆**（`remember`
的 `{"reply": ctx.reply}`）⇒ 本会话笔记里已出现 `tool_id` 转储（`~/.core/state/notes/继续.md`）；
② 模型下一轮看到「自己的 JSON 被当答复接受」且无配对工具结果 ⇒ 0166 记录过的**反馈污染**复发。

## What Changes

- **识别面收紧（`planner._unclosed_action_payload`）**：新增**严格**判据 —— 从**最后一次**出现的
  `"tool_id"` 回退到其外层 `{`，做**字符串感知**的括号深度扫描；深度**从未**回到 0 ⇒ 该结构
  **未闭合**（截断 / 写坏）。**闭合**的尾部对象（含不含 `tool_id`、其后有无正文）一律**不**命中
  ⇒ 与 0166 的「只认尾部、宁漏勿误」逐字相容（既有 5 条 Scenario 全部保持真）。
- **失败可见**：命中时落 `LLM_PLAN_PARSE_FAILED` 的**失败态终止动作**，`reply` 为**可读提示**
  （**不含**原始 JSON）⇒ 0166 已铺好的四处同口径自动生效（`trajectory.ok=False` /
  `step_completed.failed` / `loop_finished.failed` / `LoopResult.failed` / 收尾钩子 `ok=False`）。
- **原始产出可诊断（有界、不进持久面）**：失败态终止动作另带 `Action.raw_output`（≤ `_RAW_OUTPUT_MAX`
  字符）⇒ 经 `LoopResult.raw_output` 供**呈现层折叠展示**；转录 / 记忆 / 笔记 SHALL NOT 含它。
- **成因可辨（追截断根因）**：消费 provider 的 **`finish_reason`** —— `"length"` ⇒ 提示明说
  「输出被 provider 截断」；信号不可用 ⇒ 提示为「未闭合（疑似截断或写坏）」。为覆盖**流式**路径
  （TUI 主用），`LLMChunk` 增 `finish_reason` 字段并由 provider 归一化填充（`_map_chunk` 此前**丢弃**它）。
- **TUI 折叠呈现**：承 0169 的 `_StepBlock`，在 `loop.result` 携带 `raw_output` 时挂**缺省收起**的
  步骤块（点标题展开），正文只留可读提示。

## Non-goals

- **不执行**未闭合载荷，也**不**尝试「补全 / 修复后执行」—— 半成品动作执行是新增破坏面（违 P2 取向）；
  同样**不**回溯执行**非尾部**的合法动作（0166 的「只认尾部」不动）。
- **不改**终止语义：解析失败仍以回复收尾、`loop_failed` 仍只认 `limit_reason`、转录追加口径不变。
- **不发 `max_tokens`**：本轮只把「截断」**变成可见 + 可归因**。是否以 `loop.output_reserve` 驱动请求的
  `max_tokens`（本仓 `_build_request` 至今**不下发**该字段）是**独立决策**（触及端点兼容性：部分端点
  拒绝过大 `max_tokens`）⇒ 记台账另议。
- **不动** `llm-provider` 的其余字段（`content` / `tool_calls` / `thinking` 语义逐字不变），
  亦**不动**非流式 `LLMResponse.finish_reason` 的既有口径。
- **不动** Web / APP 的呈现（新字段可忽略；SPA 零改动）。

## 风险

1. **误判**（把「解释时引用的示例」当未闭合载荷）⇒ 判据取「深度**从未**归零」，闭合示例必不命中；
   且误判的代价仅是**一次失败提示**（不执行任何动作、原始产出仍可展开查看），不产生副作用。
2. **`failed=True` 外溢**：解析失败轮的 skill 迭代 / notes 观察以失败入账 —— 正是本 change 的目的；
   既有断言（`loop_finished.failed` / `LoopResult.failed`）可能触发回归 ⇒ 四门禁全绿为验收线。
3. **`LLMChunk` 增字段**：加尾字段 + 缺省值 ⇒ 构造点零改动；测试若做**整体相等**断言需同步（门禁暴露）。
4. **零回归边界**：纯 JSON 路径、原生 `tool_calls` 路径、普通文本答复、**闭合**的尾部对象四条既有路径
   SHALL 逐字不变。
