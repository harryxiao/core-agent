# Proposal 0274 — M4 长任务 token 增长基准

## Why

`doc/00-product/product-definition.md` 的 M4 写明「长任务 token 增长随任务数呈**次线性**
（记忆外置生效）｜衡量方式：**基准任务序列测量**」，但该基准任务序列在本仓**不存在** ——
M4 既不可证伪也不可证实（PA-10）。记账口径在 `0152` / ADR-0144 已修对
（`LLMPlanner.last_prompt_tokens()` 探针覆盖系统提示与工具 schema），harness 成本已足够低。

## What Changes

- 新增 `tests/test_m4_token_growth.py`（离线确定性 harness）：
  - 固定任务序列 × 24 轮，在**同一会话**内驱动真实 `DefaultLoop`（`LLMPlanner` ＋ 桩
    provider ＋ 本地有界摘要器）；
  - 逐轮采集 `LLMPlanner.last_prompt_tokens()` 曲线，输出斜率；
  - 以「关闭摘要器与维护节拍、全量原文回灌」为**线性基线**，判定外置曲线是否次线性。
- 场景对照：外置运行（维护节拍按轮触发 ⇒ 会话摘要 ＋ 中层摘要 ＋ 三层滑窗）vs 线性基线。
- 纯离线：零网络、零真实模型；注入**步进时钟**（每轮 +1s）⇒ 维护节拍确定性触发。
- 另加重放确定性用例：同一 harness 两次运行逐轮曲线一致。

**不设绝对阈值门禁**（PA-10 选项 C 未采纳，阈值另行裁决）：断言只覆盖**机制性相对判据**
（远期逐轮恒定、整体斜率低于全量回灌基线），不引入需要调参的绝对 token 阈值。

## Impact

- `tests/test_m4_token_growth.py`（新，2 用例）。
- 规格：`loop` **ADDED** 1 req（长任务 token 增长基准 + 4 scenarios）。
- 文档：`doc/00-product/product-definition.md`（M4 行补「衡量落地」）、
  `doc/04-testing/test-cases.md` §186、ADR-0264 / 台账 E210。
- **零 `src/` 改动**。

## 不做（明确边界）

- 不做绝对阈值 / CI 门禁（选项 C）、不做真模型长跑基线（选项 D）。
- 不度量任务成功率或输出质量；不引入新依赖、不改生产路径。
- 不替代 `tests/test_loop_token_accounting.py` 的记账单测（本文件测的是**曲线**）。
