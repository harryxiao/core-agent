# 0293 — 供应商输出上限能力适配与终止原因归一

## Why

`loop.output_reserve`（缺省 `8192`）自 change `0183` 起作为请求侧 `max_tokens` 下发。
但各供应商的**上限字段与数值并不统一**：

- OpenAI o 系 / GPT-5 系要求 `max_completion_tokens`，继续发 `max_tokens` 会 400；
- 各模型最大输出不同（如 `gpt-4-turbo` / `gpt-3.5` 为 `4096`），发 `8192` 可能 400；
- 部分兼容端点用 `MAX_TOKENS` / `max_tokens` 作为 `finish_reason` 的截断别名，
  0292 的截断诊断只认 `length`，会漏报。

这正是 ADR-0174 局限②与 ADR-0175 局限④留下的坑：窗口表只推导上下文窗口，未推导输出上限。
0292 让截断「可见」，本 change 让请求「不被常见方言拒绝」并把截断信号统一。

## What Changes

- **内置模型输出能力表**（`configuration/model_capabilities.py`，纯常量 + 纯函数）：
  「模型名子串 → {最大输出, 上限字段, 是否支持 reasoning_effort}」；未收录 = 不知道
  （最大输出 `0`），不钳制、不告警。
- **请求体适配**（`StdlibLLMProvider._build_body`）：有效上限 =
  `min(output_reserve, 已知最大输出)`；字段按能力表选 `max_tokens` /
  `max_completion_tokens`；SHALL NOT 同时发两个字段。未收录模型请求体逐字不变。
- **终止原因归一**：`max_tokens` / `MAX_TOKENS` / `max_output_tokens`（大小写不敏感）
  → `length`，同时作用于流式与非流式；其余取值原样保留。
- **配置期仅告警**：预留高于已知上限、或显式 `reasoning_effort` 对已知不支持模型 ⇒
  校验告警，不阻断、不丢弃配置。

## Non-goals

- 不内置各家 tokenizer，不按估算反推供应商上限；
- 不启动期探测 `/models` 或输出上限（网络依赖与启动不确定性）；
- 不在 `length` 时自动加倍重试，不改 `output_reserve` 语义；
- 不新增配置键（无 `llm.max_output_tokens` / `llm.max_tokens_field`）；
- 不把 `reasoning_effort` 按能力表静默丢弃（只告警，显式配置仍下发）；
- 不改 `known_window` 的既有窗口值，不做 `context_window` 表更新。

## Impact

- 代码：`src/core/configuration/model_capabilities.py`（新）、
  `src/core/configuration/manager.py`（能力告警）、
  `src/core/llm_provider/stdlib_provider.py`（请求体限额/字段 + `finish_reason` 归一）。
- 规格：`llm-provider` MODIFIED ×2（终止原因归一 / 请求侧输出上限）、
  `configuration` ADDED ×1（已知模型能力告警）。
- 测试：能力表、请求体契约、终止原因别名、配置告警。
- 文档：ADR-0283、`coding-plan/known-risk.md` E229、`doc/04-testing/test-cases.md` §206、
  `doc/02-modules/llm-provider.md`、`doc/03-interfaces/llm-provider-interface.md`、
  `doc/03-interfaces/configuration-interface.md`。
