# Proposal 0277 — 记忆内容分区权重（tags 三档，PA-09 方案 C）

## Why

PA-09 的检索面降级里只剩「分区权重」可在不翻案存储/依赖的前提下落地：蓝图要求
「里程碑区权重拉满 / 关键决策区 / 过程日志区最低」，而当前 `relevance` 只有
**L0–L4 稳定度轴**（`layer_priority`）—— 它衡量的是「记忆有多稳定」，**不是内容有多重要**，
于是过程日志与关键决策同权。`0276` 已把 1 万条检索压到中位 ≈86ms 并建立规模基线，
本 change 可在此基线上直接评估分区收益。

## What Changes

- `src/core/memory/relevance.py`：`relevance` 增加一维**加性**分区权重
  `w_tier · tier(entry)`（`_W_TIER = 0.15`）：
  - 高档（`tags` 含 `milestone` / `decision`）⇒ 1.0；
  - 默认档（其余，含未知/无标签）⇒ 0.5；
  - 低档（`tags` 含 `log` / `transcript`）⇒ 0.0；
  - 同一条目同时命中高低档 ⇒ **高档优先**；标签**精确匹配、小写**约定。
- 默认**开启**（用户裁决）；默认档是常量偏移 ⇒ **未打标签条目的相对排序逐位不变**，
  层优先级 / 时间 / 复用 / 重要度调制语义不变。
- 更新 `tests/test_memory_lexical_scoring.py` 的精确值断言（+ 默认档项）；
  新增 `tests/test_memory_tiers.py`（三档定序 / 冲突与未知 / 端到端 store 排序 / 同档不变）。
- 基准不回退：`0261`（26 条）与 `0275`（1 万条）的 recall/MRR 阈值维持 1.000 口径。

## Impact

- `src/core/memory/relevance.py`（+ 常量与判定函数）。
- 测试 +5 左右；`0261` / `0275` 基准不改语料。
- 规格：`memory` **ADDED**「内容分区权重（tags 三档）」。
- 文档：ADR-0267 / 台账 E213 / `doc/04-testing/test-cases.md` §189 /
  `doc/02-modules/memory.md` / `doc/03-interfaces/memory-interface.md` §3 /
  `coding-plan/Pending-Arbitration.md`（PA-09 C 标已闭，D/E 仍开放）。

## 不做（明确边界）

- 不改 `layer_priority`、BM25、分词、时间/复用/重要度调制；不做乘法权重。
- 不引入配置开关（用户裁决缺省开启）；不做自动打标（tag 由写入方显式给出）。
- 不做图（D）与真语义（E）；不改 `exclude_source_prefixes`；零三方依赖。
