# Design: async 接口契约与流式编排（acompletion/ainvoke/arun/astream）

## Context

全库英文 `async` 关键字 0 处、中文「异步」15 处均为描述性（「异步落盘/加载」），无任何异步接口契约；三个热路径接口全同步：`llm-provider` 仅 `completion`/`stream`/`embedding`，`tool-use` 仅 `invoke`，`loop` 仅 `run`（来源：exploration_findings.md，2026-09-25）。实际任务存在真并发（orchestration 已有「并行扇出 fan-out」4 Scenario，L70-91）与流式编排（逐 token 产出）需求，但「并行执行单元」与 LLMProvider/ToolProvider 的 async 能力之间无显式契约映射——同步接口在扇出场景串行阻塞、在流式场景只能一次性返回完整结果。`architecture-overview.md` L111 留痕句亦将 `ainvoke` 记为「预留接口，待实现期落地」。

## Decisions

1. **async 为主 + sync 薄壳**（决策1A）：新增 `acompletion`/`astream`/`aembedding`（llm-provider）、`ainvoke`（tool-use）、`arun`/`astream`（loop）异步变体为契约主体；既有同步方法保留为薄壳，内部经 `asyncio.run` 复用异步实现，单实现源、不破坏既有调用方。
2. **a 前缀命名延续**（探索发现）：项目已用 `ainvoke` 变体（a 前缀），统一沿用 `acompletion`/`astream`/`aembedding`/`ainvoke`/`arun`，不引入新命名约定。
3. **loop 加 astream 流式产出**（决策2A）：`astream` 返回 `AsyncIterator[LoopEvent]`，LoopEvent 事件类型=loop_started/step_completed/reply_delta/loop_finished/loop_failed 五类，覆盖执行生命周期的流式可观测性。
4. **扇出执行单元映射 async**：orchestration「并行扇出」的执行单元显式复用 `acompletion`/`ainvoke` 异步接口，消除同步串行阻塞，闭合「并行编排 ↔ 异步能力」的契约空白。
5. **纯文档落地**（决策3A）：本次仅接口契约与设计文档（src=0），异步工程实现留待后续任务；不新增 capability，仅扩展既有 4 个 capability（llm-provider/tool-use/loop/orchestration）。

## Risks

- **sync/async 双接口维护成本**：sync 薄壳经 `asyncio.run` 复用异步实现，保持单实现源，规避双份逻辑漂移。
- **asyncio.run 嵌套风险**：在已有事件循环内调用 sync 薄壳会抛错，契约须约定「sync 薄壳仅在无事件循环上下文调用」。
- **与既有同步 Requirement 语义重叠**：async 变体为扩展而非替换，不动既有 Requirement 正文；llm-provider L49「模型调用可靠性」（retry/timeout/keep-alive）已存在，本次不重复定义。
- **LoopEvent 事件粒度未定**：五事件为 MVP 粒度，reply_delta 与底层 token chunk 的边界留待工程实现收敛，契约只定义事件类型语义。

## Open Questions

- sync 薄壳 `asyncio.run` 在检测到运行中事件循环时的降级策略（拒绝 vs 桥接）待工程实现明确。
- `loop.astream` 的 LoopEvent 与 `llm-provider.astream` 的 chunk 映射关系（逐 token vs 逐 step 事件）待落地选择。
- 工程实现期是否引入 asyncio 之外的并发原语（anyio/trio 等），本次契约不锁定，仅约定标准 `async`/`await` 与 `AsyncIterator` 语义。
