# Proposal 0230: 修复记忆机制对长任务支持的缺口

## Why

对 `src/core/memory/`、`context/`、`loop/`、`orchestration/` 的长任务支持走查发现：分层记忆骨架（滚动摘要、keyfact 抽取、会话隔离、预算裁剪、断点恢复契约）均已到位，但存在若干直接影响长任务存活与记忆质量的结构性缺口，集中在**溢出降级路径**与**测量精度**两类。

走查缺口清单（附位置证据）：

- **G1（P0）token 估算过粗**：`context/budget.py:17`、`store.py:43` 采用「约 4 字符≈1 token」启发式，中英混排/代码场景偏差可达 2×，导致预算误判（假溢出提前裁剪或真实溢出漏裁）。
- **G2（P0）溢出只终止不降级**：`loop/default.py:499-501` 在 `token_used >= token_budget` 时直接 `TOKEN_BUDGET_EXCEEDED` break，长任务在临门一脚被预算杀掉且无法自动恢复。
- **G5（P1）L2 活跃层无总量上限**：`store.py` 仅有 `forget(threshold)` 与 L4 迁移路径，活跃层无硬上限；超长会话若压实节奏跟不上写入，检索面无限膨胀。
- **G4（P1）KeyFact 跨批次去重缺失**：`store.py:162-192`（`_plan_key_facts`）仅做批内去重，跨压实批次同实体可重复累积（靠 tags 前缀覆盖，非合并）。
- **G7（P2）scheduler checkpoint 是回调契约**：`scheduler.py:117,261` 的 `CheckpointFn` 需上层注入，缺省不落盘，开箱即用场景无断点恢复。
- **G3/G6（P3，仅记录不改）**：摘要依赖注入模型、`_elide_summary` 首尾截断丢中段——属 ADR-0045 刻意设计（保守缺省、有省略标记），本 change 不动。

## What Changes

本 change 只做 G1/G2/G5/G4/G7 的**确定性子集**，不做 LLM 主题聚类等行为变更：

1. **G1 — 可注入的精确 tokenizer**：新增 tokenizer 注入点（缺省保持现有启发式，行为不变）；注入精确 tokenizer 后预算测量替换启发式估算。
2. **G2 — 溢出降级续跑**：预算触顶时先触发一次 compaction 再重试一轮，二次仍超限才 `TOKEN_BUDGET_EXCEEDED` 终止（复用 change 0182 的 `compacted` 闸门防重入）。
3. **G5 — L2 活跃层软上限**：为活跃层加软上限，超限触发既有 `forget(threshold)` / L4 归档路径，不新增删除语义。
4. **G4 — KeyFact 跨批次按 slug 合并**：同实体 slug 命中时更新既有条目 value（含留痕），而非新增；批内归并语义（change 0172）保持不变。
5. **G7 — 缺省文件型 checkpoint**：为 scheduler 提供缺省文件型 `CheckpointFn` 实现，上层注入仍可覆盖。

明确不做：G3/G6 的注入式摘要缺省行为与截断策略（ADR-0045 刻意设计）；抽取端主题聚类（另行提案）。

## Impact

- **影响规格**：`doc/openspec/specs/memory/spec.md`（G4/G5）、`specs/agent-loop`（G1/G2，若预算测量与溢出行为有既有条目）、`specs/orchestration`（G7）。
- **影响代码**：`src/core/context/budget.py`、`src/core/memory/store.py`、`src/core/loop/default.py`、`src/core/orchestration/scheduler.py`。
- **兼容性**：所有改动缺省行为不变（启发式 tokenizer、无软上限、注入式 checkpoint），仅在显式配置/注入时启用新路径；写入操作继续走 `EffectTracker.record`。
- **测试**：G1 精确/缺省 tokenizer 双路径；G2 一次降级成功、二次超限终止；G5 超限触发 forget；G4 跨批次同 slug 合并不新增条目；G7 缺省 checkpoint 落盘与注入覆盖。
