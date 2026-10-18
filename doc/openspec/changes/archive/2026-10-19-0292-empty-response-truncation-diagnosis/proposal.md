# 0292 — 空响应的截断成因诊断

## Why

2026-10-19 真实冒烟（session `03c49ecf…`）：第二轮开放式问题约 89 秒后返回
`LLM_PLAN_PARSE_FAILED: 空响应`。复现确认根因是 GLM-5.3 默认深度思考把本次请求的
`max_tokens`（= `loop.output_reserve`，8192）全部耗在 `reasoning_content` 上，
`content` 为空、`finish_reason="length"`。规划器 `_parse` 在内容为空时**先判空、后不看
`finish_reason`**，于是把「输出预算耗尽/被截断」误报为无成因的「空响应」，用户与排障者
无法从回复中区分「模型没说话」「网络空包」「思考吃满预算」三种情况。

## What Changes

- **空内容分支利用 `finish_reason`**（`LLMPlanner._parse`）：内容去除首尾空白后为空且
  provider 报告 `finish_reason="length"` 时，`reply` 明示「输出被截断 / 输出预算可能被思考
  耗尽」；`finish_reason` 缺失、空串或非 `length` 时，维持既有
  `LLM_PLAN_PARSE_FAILED: 空响应` 逐字文案。
- **失败语义不变**：仍是失败态终止动作（`failed=true`、`ok=False`、零工具执行、无原始产出）；
  非空内容的所有解析分支（五形态、回喂重试）逐字不变。

## Non-goals

- 不改变 token 预算 / `max_tokens` 的分配（不自动加大 `output_reserve`）。
- 不做自动降档重试、不探测思考长度、不修改 provider 请求形状。
- 不新增配置项、不新增错误码、不改变 `LLM_PLAN_PARSE_FAILED` 前缀。
- 不改变非空内容与工具调用路径的任何行为。

## Impact

- 代码：`src/core/loop/planner.py`（`_parse` 空内容分支）。
- 规格：`loop` 一条 MODIFIED delta（「推理动作解析与失败可见」＋两个 Scenario）。
- 测试：`tests/test_loop_output_protocol.py` 新增用例；全量回归。
- 文档：ADR-0282、台账 E228、test-cases §205、loop 模块文档的失败措辞说明。
- 缺省行为：仅 `finish_reason="length"` 的空内容提示变化；其余逐字不变。
