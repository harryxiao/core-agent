# Proposal 0222 — 夹带的动作 JSON 归一为可见失败（PA-01，capability `loop`）

## Why（缺口）

`loop` 解析器对「**闭合的动作 JSON + 尾随正文**」（动作对象**不在**文末，其后仍有正文）的形态，
旧实现落到 `planner._parse` 的兜底 `return Action(args={"reply": text})` ⇒ **整段 JSON 被当成最终
答复**：动作丢失（零执行）、本轮记为**成功**、JSON 进转录与记忆。这是 change `0166`／ADR-0156 当年
只堵了「正文 + **尾部** JSON」、未堵反向所留的缺口（`coding-plan/Pending-Arbitration.md` PA-01 现象①）。

本轮提词收紧（`1f93b88`）把提示收紧为「JSON 必须是整条回复的第一个字符，其后不得再有任何字符」，
**覆盖了模型守规矩的情形，但不构成防线**（模型可违反）。

## What Changes

1. **`src/core/loop/planner.py`**：新增形态 5 判据 —— `_embedded_action_payload(text)`：扫描文本，
   存在**已闭合**的可解析 JSON 对象、含**非空** `tool_id`、且其后仍有非空白正文 ⇒ 命中。`_parse`
   在该情形返回**失败态终止动作**（新常量 `_UNPARSED_EMBEDDED`，带 `raw_output` 有界留存），
   `SHALL NOT` 执行该动作、`SHALL NOT` 当回复。
2. **规格 delta（`loop` MODIFIED）**：Requirement「推理动作解析与失败可见」由**四种**形态扩为
   **五种**；新增形态 5；改写「正文中间夹带一律按回复」句为「夹带的**非动作** JSON（无 `tool_id`）
   仍按回复；夹带的**动作** JSON（含非空 `tool_id`）归一为形态 5」；MODIFIED「非动作 JSON 的自然
   语言回复不被误判」Scenario；ADDED「夹带的动作 JSON 归一为可见失败」Scenario。
3. **ADR-0212**：**取代** ADR-0156 的「只认尾部、宁漏勿误」在该子情形上的语义（历史 ADR 不改写）。
4. 测试：改写 `test_action_json_mid_text_stays_reply`（旧语义）与
   `test_closed_tail_object_without_tool_id_stays_reply`（名实不符，实为形态 5），新增两用例。

## 显式不做

- **流式泄漏（PA-01 现象②）不做**：`planner.astream` 用**首个非空 chunk 首字符**判形态、判为回复后
  其后所有 chunk 原样外发，会漏出尾随 JSON。根治须**放弃边出边流**（全缓冲）—— 属产品级交互取舍
  （首字延迟 vs 正确性），**单独立项**（PA-01 可选项 C），不在本 change。
- **不执行**夹带的动作 JSON（不做「JSON 在正文中间该不该执行」的启发式猜测）—— 只归一为失败。
- 不改 `_trailing_json_object` / `_unclosed_action_payload` 的既有判据（形态 3 / 4 逐字不变）。
