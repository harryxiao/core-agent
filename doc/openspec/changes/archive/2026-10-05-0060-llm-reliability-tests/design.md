# 设计：llm-reliability-tests（E11①）

## 1. 为什么不改生产代码

9 例全部**一次通过**。这说明 `stdlib_provider.py` 的可靠性面在写它时就是对的——缺的是
**可回归的证据**。本变更因此是**纯验证变更**：新增用例即产出物，`src/` 零改动。

反过来说也成立：这批用例的价值不在今天（今天全绿），而在**将来有人改 provider 时**——
退避改成立即返回、降级顺手删掉、断流改成「吞掉异常直接结束」，都会被这 9 例抓住。

## 2. 接缝选择（打桩在哪一层）

| 用例组 | 打桩点 | 理由 |
|---|---|---|
| 退避口径 | 无（直接调 `_backoff`） | 纯函数，口径即断言 |
| 重试 / 超时 / 降级 | `provider._call_provider`（异步单请求） | 绕开 HTTP，**保留** `acompletion` 的重试循环 / `asyncio.wait_for` / `models` 遍历——正是被测对象 |
| 断流 | `stdlib_provider.urllib.request.urlopen`（返回假响应） | 断流发生在 **SSE 逐行迭代**里，必须让真实 `_iter_sse_payloads` 参与，否则测的是 mock |

**唯一未打桩的边**是 `_backoff` 的等待——用例把它 patch 成 `0.0`（`_no_sleep`），否则退避
`0.5+1.0+2.0 = 3.5s` 会拖慢套件。退避**数值口径**由 `test_backoff_is_exponential_and_capped`
单独覆盖，两例合起来仍完整（数值 + 次数）。

**断流的惰性生成器**（`_lines()`）是刻意为之：首版把 `list(_lines())` 传进去，`URLError` 在
**进入 provider 之前**就抛了，等于什么都没测。改为传生成器 → 异常在 `_iter_sse_payloads`
迭代中途出现，才真正压到「先给已收内容、再抛归一化错误」这条路径。该处 `got.append` 带
`# noqa: PERF401`：**不能**改成推导式，否则中途异常会把已收部分一起丢掉（正是被测语义）。

## 3. 覆盖与规格 Scenario 的映射

| 规格 Scenario | 用例 |
|---|---|
| 失败自动重试 | `test_backoff_is_exponential_and_capped` / `_acompletion_retries_until_success` / `_retry_exhausted_raises_normalized_error` / `_non_retryable_error_is_not_retried` |
| 调用超时控制 | `test_call_timeout_is_enforced` |
| 服务降级 | `test_degrades_to_fallback_model` / `test_non_retryable_error_does_not_fall_back` |
| 流式断流处理 | `test_stream_without_done_marker_returns_partial` / `test_stream_mid_transport_error_surfaces_partial_then_raises` |
| 连接复用 | **未覆盖**（未实现，E11②） |

四条已实现的 Scenario **全部**有对应用例；未实现的第五条不含在内——本变更**不**为未实现的行为
写用例，也不假装它已覆盖（其状态在 proposal「规格中性」与 §5「遗留」中明写）。

## 4. 为什么用 `skip_specs: true` 而不是造一个 delta

四场景无行为改动 ⇒ 规格无 Requirement 需改。OpenSpec 的默认契约是「变更必有 spec delta」，
对本仓是首次遇到**合法**的无 delta 变更（此前无先例）。机制核实过程：以临时
`0060-probe` 变更逐项试 `openspec validate`，确认变更目录下 `.openspec.yaml` 同时给
`schema: spec-driven`（缺失则报 `expected string, received undefined`，`skip_specs` 不被采信）
与 `skip_specs: true` 时，才被判定为**规格中性变更**并跳过 delta 校验，随后删除探针。
该 yaml 即本变更目录下的 `.openspec.yaml`。

不选「写一个占位 delta」：没有 Requirement 要改，占位 delta 是**假规格**，比缺失更坏。

## 5. 遗留（不属本变更）

- **E11② 连接复用**：规格已声明、实现未落地。关闭它需要：`http.client.HTTPConnection`
  长连接（或池）+ 失效重建 + 并发下的所有权模型，并配 ADR。**待定夺**是否值得在
  stdlib provider 上自建（Phase 1 的 provider 是「零依赖基线」，真跑量产流量通常换
  `litellm`/`openai` 适配器——`runtime.py` 已按 provider 名分流，故自建池的收益需先论证）。
- **真机冒烟**：本轮验证是离线的（打桩 HTTP）。活 LLM 端到端属 §9 第 10 步。
