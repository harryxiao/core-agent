# Proposal — 退化 JSON 的转义与内引号修复（change 0321）

## Why

2026-10-24 14:13–14:14，子 Agent 在完成 6 轮勘察后失败（trace `a36c6cff5a064745add1b42340cea65a`）。
模型交出的动作对象**结构完整**，但两处字面量写坏：

```json
{"tool_id": "tools.code_run", "args": {"script": "… grep -i "memory\|write\|deactiv" …"}}
```

- 字符串内的双引号**未转义**（`"memory…"`）；
- 反斜杠转义**非法**（JSON 只认 `\" \\ \/ \b \f \n \r \t \uXXXX`，`\|` 不是）。

`json.loads` 必然失败；既有恢复链（混写 `<parameter>` / 截断补括号）均不命中 ⇒ 落到通用
「`LLM_PLAN_PARSE_FAILED: 无法解析模型输出为动作`」，整轮作废、零执行。`loop.parse_retry`
缺省**关**（spec 明文），因此没有回喂重试，6 轮工具结果全部白费。

这两类退化**没有任何语义歧义**：模型想执行的命令就是它写出来的那段文本，只是忘了 JSON 转义。
确定性修复比再发一次模型调用更便宜，也更稳。

## What Changes

- **A. 确定性字面量修复**：`_parse` 在「`{` 开头、`json.loads` 失败」分支、且既有恢复链
  （`_recover_truncated_tool_json`）不命中后，做**一次单遍字符串感知扫描**：
  - 字符串内**非法反斜杠转义**（反斜杠后不是合法转义字符）⇒ 补成字面反斜杠（`\|` → `\\|`）；
  - 字符串内**双引号**仅在其后首个非空白字符为 `,` `:` `}` `]` 或内容结束时视为闭合，
    否则补转义（`"memory…"` → `\"memory…\"`）。
- **B. 采纳门槛**：修复结果必须可解码为 **dict**，且含非空 `tool_id` 或非空 `reply`；否则
  不采纳，维持既有「无法解析」失败语义与提示。
- **C. 不做结构补全**：修复**不**补缺失的括号 / 引号 ⇒ 未闭合 / 截断形态维持既有失败语义与
  `raw_output` 留痕；已存在的字符串字符一个不删、不换。
- **D. 顺序**：修复位于既有恢复链之后、失败动作之前；修复成功即走 `_from_dict` 既有语义
  （工具动作 / 终止动作），不触发 `loop.parse_retry`。

## Impact

- 代码：`src/core/loop/planner.py`（新增一个纯函数 + `_parse` 一处调用）。
- 规格：`loop`「推理动作解析与失败可见」MODIFIED（补充修复规则与 3 条 Scenario）。
- 测试：新增 `tests/test_degenerate_json_repair.py`（事故复刻 + 不越界恢复 + 门槛）。
- 配置：**零新键**；`loop.parse_retry` 缺省仍关。

## Out of Scope

- 不做通用 JSON5 / 容错解析器，不引入第三方依赖；
- 不修复未闭合 / 截断 / 尾部夹带 / 正文混写等既有形态（各自已有恢复或失败语义）；
- 不改 `loop.parse_retry` 缺省值，不改流式超时与重试语义（另案，先验证 change 0320）。
