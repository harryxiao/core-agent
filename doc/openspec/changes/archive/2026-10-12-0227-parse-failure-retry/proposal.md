# Proposal 0227 — 解析失败回喂重试 ＋ 首字符花括号失败成因细化

## Why

2026-10-11 23:36 实跑事故（session `88a6a6b9…`，trace `1c7cfb24…`）：delegate 子 Agent 在长上下文
压力下（maintenance HTTP 400 → turn observer 超时 >60s）最终一轮产出**退化重复**形态 —— 完整动作
JSON 缺最外层收尾 `}`、后随字面省略号垃圾与第二份重复对象、5029 字符处截断。该输出以 `{` 开头，
`_parse` 的首字符分支整体 `json.loads` 失败 ⇒ 通用文案「无法解析模型输出为动作」、终止回复、
**无重试** ⇒ 子 Agent 5.6 分钟工作（第一份对象里 proposal 内容已完整写出）全部丢弃。

两个缺口：

1. **无自愈**：解析失败被当作终止回复 ⇒ loop 直接结束，模型看不到自己的协议违规、没有重试机会
   （「失败可见」只有用户可见，没有模型可见）。ReAct 的容错闭环缺了回喂这一环。
2. **诊断粒度**：`{` 开头＋整体解析失败只有通用文案 —— 形态 4（未闭合/截断）与形态 5（夹带正文）
   的成因判据在该分支**不可达**（0170/0222 只覆盖「内容不以 `{` 开头」的路径），`finish_reason`
   亦被忽略。本案实为「未闭合（疑似截断或写坏）」，用户却只看到笼统错误。

## What Changes

- **回喂重试（承重）**：`LLMPlanner` 新增 `parse_retry`（缺省关）。开启时，解析失败
  （`LLM_PLAN_PARSE_FAILED` 各分支）且本轮**未外发任何内容增量**的场合，以同一上下文追加一条
  用户消息（**失败成因 ＋ 输出格式协议重申**，绝不携带原始退化产出）后重试**恰一次**；重试可解析
  ⇒ 按正常结果处理；仍失败 ⇒ 维持既有失败语义（逐字）。已外发内容增量的流式场合不重试。
- **成因细化**：`{` 开头整体解析失败的分支复用形态 4/5 判据 ＋ `finish_reason` —— 命中未闭合 ⇒
  「未闭合/被截断」措辞；命中夹带（含**对象在前、正文在后**）⇒「动作 JSON 之后仍跟有正文」；
  皆不命中 ⇒ 维持通用文案。**只改提示信息量，失败语义不变**。
- **配置**：新键 `loop.parse_retry`（bool，缺省 `false`，ADVANCED；yaml/env/CLI 三面）。
- **接线**：组合根算一次、注入**四个 loop** 的全部 planner（与 `max_tokens`/`block_plan` 同型）。

## Impact

- **规格**：`loop` MODIFIED「推理动作解析与失败可见」（成因措辞条款扩到 `{` 开头类 ＋ 新增重试
  段 ＋ ADDED 6 Scenario；既有 8 Scenario 逐字保留）。
- **代码**：`src/core/loop/planner.py`（新 `_RETRY_NUDGE` 常量、`_retryable`/`_retry_nudge`/
  `_first_brace_reply`、`_complete` 拆两 attempts、`astream` 拆 `_astream_once` 递归一层）；
  `src/core/configuration/manager.py`（键 ＋ 访问器 ＋ `_loop_errors` 校验）；`src/core/runtime.py`
  （四 planner 接线）。
- **提词面**：新 prompt 常量 `_RETRY_NUDGE` ⇒ pin（`test_prompt_pinning`）＋ 镜像（`prompts.md` ⑮）
  ＋ 镜像门禁（`test_prompt_mirror` 落点列 ①~⑮）三处同改。
- **零回归承诺**：缺省关 ⇒ 请求形状、调用次数、失败语义逐字不变。
