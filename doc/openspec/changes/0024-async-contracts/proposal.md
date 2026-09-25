# Change: 补齐异步接口契约与流式编排（acompletion / ainvoke / arun / astream）

## Why

全库英文 `async` 关键字 0 处，中文「异步」15 处均为描述性（「异步落盘/加载」），无任何异步接口契约；三个热路径接口全同步：`llm-provider` 仅 `completion`/`stream`/`embedding`，`tool-use` 仅 `invoke`，`loop` 仅 `run`（来源：exploration_findings.md，2026-09-25）。实际任务存在真并发（多工具并行扇出）与流式编排（逐 token 产出）需求：同步接口在扇出场景串行阻塞、在流式场景只能一次性返回完整结果，与 orchestration 既有「并行扇出 fan-out」能力矛盾。PocketFlow 对比已论证「sync/async 同构」是可吸收的工程技巧，本次将其固化为接口契约。

## What Changes

- **llm-provider**：新增异步变体 `acompletion`/`astream`/`aembedding`（asyncio 协程）；既有 `completion`/`stream`/`embedding` 保留为薄壳（内部 asyncio.run 独立事件循环调用异步实现）。
- **tool-use**：新增 `ainvoke` 异步变体；`invoke` 保留为薄壳。
- **loop**：新增 `arun` 异步执行 + `astream` 流式执行（产出 `AsyncIterator[LoopEvent]`），定义 LoopEvent 五事件：loop_started / step_completed / reply_delta / loop_finished / loop_failed。
- **orchestration**：新增「异步执行单元契约」，明确并行扇出的执行单元复用 `acompletion`/`ainvoke` 异步接口，消除契约空白。
- **03-interfaces**：三个接口文档补异步方法签名与 LoopEvent 定义。
- **adr.md**：追加 ADR-0033（async 为主 + sync 薄壳的接口同构决策）。
- **architecture-overview.md**：L111 留痕句「异步化能力作为预留接口待落地」→「异步契约已定义，sync 为薄壳」。

## Impact

- **Affected specs**：`llm-provider`（+异步调用接口 Requirement）、`tool-use`（+异步工具调用 Requirement）、`loop`（+异步流式执行 Requirement）、`orchestration`（+异步执行单元契约 Requirement）——均为扩展既有 capability，不新增 capability
- **Affected docs**：`03-interfaces/llm-provider-interface.md`、`03-interfaces/tool-use-interface.md`、`03-interfaces/loop-interface.md`、`01-architecture/adr.md`（+ADR-0033）、`01-architecture/architecture-overview.md`（L111 留痕句改写）
- **Affected code**：无（接口契约与设计文档落地；工程实现依赖后续任务）
- **Dependencies**：ADR 编号=当前最大+1（0033）；sync 薄壳复用 asyncio.run（不引入新框架）；扩展既有 capability → 不动 requirements.md 数字口径、不动 architecture-overview 横切计数
