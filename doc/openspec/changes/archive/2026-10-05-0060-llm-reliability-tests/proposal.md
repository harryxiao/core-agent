# 补齐模型调用可靠性用例（llm-reliability-tests）

## Why

账本 E11：`phase-1.md:30` 的验收框「失败自动重试、超时控制、服务降级、连接复用、流式断流处理」
**至今未勾**。一手核实（读 `src/core/llm_provider/stdlib_provider.py` + 全仓测试）后确认，
该框下**两件事性质不同**，须拆开：

1. **四条可靠性路径已有实现、零用例**：重试（`_completion_with_retry`：`max_retries+1` 次 +
   `_backoff` 指数退避 + `asyncio.wait_for(timeout)`）、降级（`acompletion` 遍历
   `[request.model, *fallback_models]`，非可重试错误 `break`）、断流
   （`_iter_sse_payloads` 遇 `[DONE]` 停；中途异常经队列项**在已 yield 的块之后**抛归一化错误）。
   即「Phase 1 验收未达成」的直接原因不是缺实现，而是**缺验证**——规格
   「模型调用可靠性」的四条 Scenario 在生产无处可证明。
2. **连接复用（keep-alive / 连接池）确未实现**：`urllib.request.urlopen` 每请求新建连接。
   这是**实现变更**（需 `http.client` 长连接或自建池），在零三方依赖红线下要单独立项 + spec delta。

本变更只做 ①。② 保持账本 E11 的未闭部分，**不在本变更内**。

## What Changes

- **`tests/test_llm_provider.py` 增一节「模型调用可靠性」（9 例）**，逐条对应规格 Scenario：
  - 退避口径：`_backoff(1..4) == [0.5, 1.0, 2.0, 4.0]` 且封顶 `8.0`；
  - 重试：瞬时错误重试至成功（调用数 = 1 + `max_retries`）；重试耗尽抛**归一化**异常（不泄漏底层）；
    非可重试错误（鉴权）立即抛、不重试；
  - 超时：慢调用不拖住调用方（`timeout=0.05` 下实测耗时 < 1s 且抛 `LLMTimeoutError`）；
  - 降级：主模型失败 → 切备用模型成功，且审计记**实际成功的模型**；非瞬时错误**不**降级；
  - 断流：无 `[DONE]` 提前结束 → 部分返回不挂起；传输中途异常 → **先给已收内容再抛**
    `LLMNetworkError`。
- **不改任何生产代码**：9 例全绿即为「实现正确」的证据；若有用例转红，才是实现缺陷。

## 规格中性（`.openspec.yaml: skip_specs: true`）

- 四场景**行为早已存在**，本变更只补验证 → 无 Requirement 改动，故不产出 spec delta。
- **遗留在规格内的未达成项**：`llm-provider` 规格「模型调用可靠性」正文含
  **底层连接复用（connection reuse / keep-alive）**——该条**当前未被实现**，属账本 **E11②**。
  本变更**不**因此改规格（既不删该条以掩盖差距，也不加「待办」注记以污染规格）；
  该条待 E11② 单独立项时随 ADR 处理。

## 明确不做

- **不做连接复用**（E11②，实现变更 + spec delta + 需先定夺「是否为 stdlib provider 自建连接池」）。
- **不做真后端连通性冒烟**（需活 LLM，属 §9 第 10 步「真机动作」，与本变更的离线验证互补）。
- **不改断言既有用例**（外科手术式改动；既有 `test_llm_provider.py` 用例一字未动）。
- **不新增三方依赖 / 不引入本地 mock server**（红线；用例在 provider 边界用 `mock.patch` 打桩，
  见 design「接缝选择」）。
