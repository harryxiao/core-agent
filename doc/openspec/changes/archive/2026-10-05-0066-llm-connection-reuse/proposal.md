# LLM 传输层连接复用（llm-connection-reuse / 账本 E11②）

## Why

账本 **E11②**（change `0060` 收口时记下的剩余项）：「`urllib` 每请求新建连接（无 keep-alive）」。

规格 `specs/llm-provider/spec.md`「模型调用可靠性」**已声明**该能力 ——
「……底层**连接复用（connection reuse / keep-alive）**、流式（stream）响应断流可恢复」，
场景「连接复用」逐字写：「**GIVEN** 多次连续模型调用 **WHEN** 发起请求 **THEN** 复用底层 connection /
keep-alive 连接，减少握手开销，**连接失效时自动重建**」。

实现里**没有**：`stdlib_provider.py` 三条传输路径（chat / embedding / SSE）各自
`urllib.request.urlopen(...)` —— 每次调用一次 TCP（+ TLS）握手。故这是
**「规格要求 X 而实现没有」**（与 E12 同型 ⇒ **改代码向规格靠拢**，不是订正规格承认现状）。

**用户裁决（2026-10-05）：实现（stdio 零依赖）** —— 不订正规格、不删条款。

## What Changes

- 新增 `src/core/llm_provider/http_pool.py`：`HTTPTransport` 协议 + `HTTPConnectionPool`
  （`http.client` + `ssl`，均 stdlib），按 origin 复用 keep-alive 连接，含失效重建 / 代理与 3xx 回落 / 未读尽丢弃。
- `src/core/llm_provider/stdlib_provider.py`：三条传输路径统一改走 `self._transport.send(request, timeout=...)`；
  新增 `transport: HTTPTransport | None = None` 构造注入接缝（DI 对齐 ADR-0040）；
  `map_http_error` 补 `http.client.HTTPException` / 其余 `OSError` → `LLMNetworkError`（连接池路径不再泄漏裸 `OSError`）。
- 新增 `tests/test_llm_provider_reuse.py`（9 例，**真实 socket**）：本地 `http.server` 桩统计 accept 数 ——
  两次调用 1 条连接 / embeddings 共用 / 按 origin 分键 / 服务端关连接后自动重建 / 429 与拒绝连接的错误归一 /
  3xx 与代理回落 `urlopen` / SSE 走同一传输层。
- `tests/test_llm_provider.py`：8 个原 patch `urlopen` 的用例改注入 `_FakeTransport`（传输接缝替换，
  断言口径不变：请求 URL / body 仍逐字断言）；错误归一用例补连接层两行。
- 文档：ADR-0064、接口 §3.1、模块 §3.6/§4、`test-cases.md` TC-LLM-06。

## 规格中性（`skip_specs: true`）

**规格不需要改**：本变更**实现**规格已声明的条款（场景「连接复用」逐字对应），属实现向规格靠拢。
故 `src` 与 `specs` 的关系是「补齐差距」，变更目录声明 `schema: spec-driven + skip_specs: true`，
把「差距已闭合」记在账本（`coding-plan/phase-19.md` E11②）而非污染规格（见 change `0060` 的边界约定）。

## 明确不做

- **不实现代理隧道（CONNECT）**：代理环境整体回落 `urlopen`（`http.client` 不读代理环境变量），
  语义等同且零风险；自建隧道属能力增量，需另立变更。
- **不做跨线程连接池**：连接存 `threading.local()`（线程内复用、无锁）。跨线程共享需锁 + 借用协议 +
  半开状态，与其收益（调用线程主要来自 1~2 个工作线程）不成比例；池化粒度是**线程 × origin**，列为已知边界。
- **不改协议 / 重试 / 退避 / 降级 / SSE 解析**：只换传输；非 2xx 一律转 `urllib.error.HTTPError`，
  既有状态码 → 领域异常映射（429/401/408/504…）逐字不变。
- **不改 `max_retries` 语义**：失效重建限定「尚未收到任何响应字节」才重发，与重试循环是两件事（不叠加放大）。
