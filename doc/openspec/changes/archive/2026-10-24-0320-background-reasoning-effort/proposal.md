# Proposal — 后台派生调用的推理档位透传（0320）

## Why

用户反馈：TUI **总有**「会话上下文压缩超时」。诊断（trace + 实测）落在**一处配置泄漏**：

`_llm_text`（组合根的后台派生模型调用接缝：会话摘要、关键事实 / 关系 / 情景归纳、SOP 提炼、
沉淀候选蒸馏、进化 review / patch author）构造 `LLMRequest` 时**只带 `messages` 与 `model`**；
而前台全部 6 处 planner 调用都带 `reasoning_effort=app.llm.reasoning_effort`（并以
`loop.output_reserve` 作 `max_tokens`）。因此用户配置的 `llm.reasoning_effort: low` 对后台
派生调用**从未生效**，端点按默认档位长时间思考：

| 实测（同一段摘要 prompt，GLM-5.3，session `9d12d78a`） | 耗时 | completion tokens | 正文 |
|---|---|---|---|
| 现状（不带档位、不带上限） | 44.8s | 4988 | 2525 字 |
| 仅 `max_tokens=2048` | 26.0s | 2048 | **0 字**（`finish=length`，思考吃满预算） |
| 仅 `reasoning_effort=low` | 10.0s | 901 | 2008 字（`finish=stop`） |
| 档位 + 上限 | 8.0s | 747 | 1635 字 |

后台 provider 单次超时缺省 60s、轮内压实总上限缺省 60s ⇒ 摘要 / 关键事实两次调用合计常
打满或超时。`~/.core/state/traces.jsonl` 中 `maintenance_failed` 59 次 vs `compaction` 10 次；
超时行恒为 `{"step":"compaction_timeout","timeout_s":60.0}`，配对的
`{"step":"memory_compact","error":"LLM_TIMEOUT: 调用超时（>60.0s）：glm-5.3"}`。超时后摘要不落库、
原条目不归档 ⇒ **下一轮同样触发**，这就是「总有」。

## What Changes

- **A（修复）** 组合根 `_llm_text` 构造 `LLMRequest` 时 SHALL 携带
  `reasoning_effort=app.llm.reasoning_effort` —— 与用户交互调用同源同值。
- **B（零变化）** `llm.reasoning_effort` 未配置（`None`）时 SHALL NOT 下发该字段，请求与引入前
  逐字一致（`StdlibLLMProvider` 只在非 `None` 时写入请求体）。
- **C（明确不做）** SHALL NOT 给后台调用引入 `max_tokens` 缺省上限：实测「只掐输出」会让
  思考吃满预算、正文为空（`finish=length`），比超时更糟。输出上界仍由后台超时与提示词上界
  （摘要 ≤2000 字、关键事实 ≤16 条 × ≤200 字）共同约束。

## Impact

- 代码：`src/core/runtime.py`（`_llm_text` 一处）。
- 测试：新增 `tests/test_background_reasoning_effort.py`（配置时透传 / 未配置不下发）。
- 规格：`configuration` ADDED ×1（「后台派生调用的推理档位透传」）。
- 文档：ADR-0310、`coding-plan/known-risk.md` E256、`doc/04-testing/test-cases.md` §233。
- **零新配置键、零新依赖、零新工具**；provider / planner / 压实契约逐字不变。

## Out of Scope

- 不发明后台专用默认档位（未配置就是不下发；如需「后台恒 low」应先有配置键与决策记录）。
- 不改 `llm.background_timeout` / `llm.background_max_retries` / `loop.compact_timeout` 的缺省。
- 不把压实移出轮内关键路径（本 change 只消除「每次都撞 60s 墙」，不改变压实仍阻塞本轮的事实）。
- 不改前台 planner 的 `max_tokens` / 档位注入。
