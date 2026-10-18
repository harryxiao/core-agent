# Proposal 0275 — 记忆检索规模基准（1 万条，PA-09 方案 B）

## Why

PA-09 的「检索质量 / 规模」长期不可判定：`0261` 的检索质量基准只有 26 条语料，覆盖排序语义
但不覆盖**规模**；产品要求 CORE-NFR-PERF2 写明「<100ms（1 万条事实规模）」，却没有任何
在 1 万条规模上测延迟或召回的文件。蓝图的分区权重（C）、图（D）、真语义（E）都以「先能证明
优化有效」为前提 —— 没有 1 万条基准，任何优化都不可验证（PA-09 选项 B）。

## What Changes

- 新增 `tests/test_memory_scale_benchmark.py`：
  - 固定 **1 万条**合成事实语料（L2 / L3 / L4 混合，每条带唯一锚点 `zqNNNNN`）；
  - 20 条带 gold 的查询，度量 **recall@5 / MRR@5** 与**逐查询延迟**（中位 / p95 / max）；
  - 准确率门禁：recall@5 ≥ 0.9、MRR@5 ≥ 0.7；
  - 语料确定性：两次独立生成逐条一致。
- 纯离线：内存 `FileBackend`、无 embedder、无真实 LLM、无网络。
- **延迟只报告、不设产品阈值门禁**：本机实测中位 **≈0.66s**，**未达** CORE-NFR-PERF2 的
  100ms 目标 —— 这是本基准揭示的既有缺口，修复另行立项；本 change 只用宽松回归上限
  （p95 < 5000ms）防止整体恶化一个数量级。
- 已知热点（cProfile）：`read()` 的 `_truncate` 对全部候选逐条调用 `estimate_tokens`
  （10k 条 × 每条逐字符 CJK 判定），占单次查询约 78% 时间；词法统计与排序占比小。

## Impact

- `tests/test_memory_scale_benchmark.py`（新，2 用例，约 20s）。
- 规格：`memory` **ADDED** 1 req（检索规模离线基准 + 3 scenarios）。
- 文档：`doc/04-testing/test-cases.md` §187、ADR-0265 / 台账 E211、
  `coding-plan/Pending-Arbitration.md`（PA-09 方案 B 标已闭，C 仍开放）。
- **零 `src/` 改动**。

## 不做（明确边界）

- 不修延迟（选项 B 明确「无产品行为改动」）；不做分区加权（C）、图（D）、真语义（E）。
- 不度量真实 LLM / embedder 的语义召回；不替代 `0261` 的 26 条排序语义基准（两者互补：
  0261 管**排序口径**，本基准管**规模与延迟**）。
- 不把 CORE-NFR-PERF2 的 100ms 写成硬门禁 —— 当前实现不达标，门禁会一落地即红。
