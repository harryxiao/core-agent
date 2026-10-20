# 0297 — 动作 JSON 后的纯 JSON 注释对象不再作废本轮

## Why

2026-10-20 子 Agent 生产事故（trace `fc82601b10ba4f598ceed49a4e0497f9`）：子 Agent 第 4 轮
输出为

```json
{"tool_id": "tools.code_run", "args": {"script": "…"}},
{"integrated_analysis": ["change 目录 … 不存在", "git 工作区有大量未提交修改", …]}
```

首个对象是**完整可执行**的动作；其后跟的是一个**纯 JSON 注释对象**（`integrated_analysis`，
含分析要点、无 `tool_id`）。当前的形态 5 判据把「动作对象之后余部含词元字符」一律视为
「追加了正文」⇒ `LLM_PLAN_PARSE_FAILED: 动作 JSON 之后仍跟有正文`，本轮作废、动作不执行。
`loop.parse_retry` 缺省关，子 Agent 直接把失败回执给用户。

这不是「动作后写解释正文」的旧事故，而是**结构化注释**被当成了散文。模型在动作后附带
一个无动作语义的 JSON 值，不改变首个动作的完整性；把它判为不可用，代价是**丢失一个已
完整写出、且无歧义的动作**。

## What Changes

- 解析器 SHALL 容忍「**首个完整动作对象 + 其后一个或多个纯 JSON 注释值**」的输出形态：
  首个对象的 `tool_id` / `args` 即动作；注释值 SHALL NOT 进入 `args`、`reply`、转录或记忆。
- 「纯 JSON 注释值」的判据 SHALL 严格且确定性：
  - 余部由一个或多个**完整** JSON 值组成（对象 / 数组 / 标量均可），值之间允许空白与可选逗号；
  - 每个**顶层对象** SHALL NOT 含非空 `tool_id`，SHALL NOT 含 `reply` 字段；
  - 注释序列之后 SHALL 只剩空白（允许收尾代码围栏）；任何含词元的余部 ⇒ 不命中。
- 以下形态 SHALL 维持既有失败语义（形态 5，可见失败、不执行）：
  - 动作后跟正文（含注释值之后再跟正文）；
  - 动作后跟**第二个动作**（顶层含非空 `tool_id`）；
  - 动作后跟 `reply` 对象（无法判定哪个才是本轮终态）。
- 提示词与回喂重试提示 SHALL 明确禁止在动作 JSON 后追加第二段 JSON（含
  `integrated_analysis` 一类分析对象）：容错是安全网，不是推荐形态。
- 本 change SHALL NOT 改变 `loop.parse_retry` 的缺省值与重试次数；SHALL NOT 改变任何
  既有失败文案或 `raw_output` 语义。

## Non-goals

- 不把注释对象合并进 `args` 或最终回复；不解析注释语义、不做「是否值得展示」的判断。
- 不容忍动作后跟 Markdown 正文 / 列表 / 表格（仍按形态 5 失败）。
- 不放宽形态 4（未闭合载荷）与形态 5 的既有判据；不改变「正文 + 尾部动作」的形态 3。
- 不为注释对象新增事件、UI 展示或记忆写入。
- 不改变 `loop.parse_retry` 缺省关闭；不引入第二次解析回喂。

## Impact

- 代码：`src/core/loop/planner.py`（新增尾随注释判据；`_parse` 的 `{` 分支；系统提示与
  `_RETRY_NUDGE` 措辞）。
- 规格：`loop` MODIFIED「推理动作解析与失败可见」。
- 测试：`tests/test_loop_output_protocol.py` 新增动作 + 注释对象 / 注释数组执行、
  第二动作 / `reply` 对象 / 注释后正文仍失败；既有形态 2/3/4/5 用例零改动。
- 文档：ADR-0287、`coding-plan/known-risk.md` E233、`doc/04-testing/test-cases.md` §210、
  `doc/03-interfaces/loop-interface.md` 与 `doc/03-interfaces/prompts.md`。
