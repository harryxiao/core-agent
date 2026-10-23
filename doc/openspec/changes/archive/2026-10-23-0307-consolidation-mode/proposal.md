# Proposal — 0307 巩固的可关闭性与水位语义

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §5.3「巩固（Consolidation）」的硬性要求与走查 **P2-1**：

1. **不可关闭**：SDD 要求 `memory.consolidation.mode: off` 时「只保留原始情景，不生成知识」。
   本仓 `MemoryStore.compact()` 的四路产物（会话摘要 / 关键事实 / 关系 / 情景归纳）中，后三者
   各有独立开关，**摘要器在组合根无条件接线**（`runtime.py` 恒传 `summarizer=summarize_with(...)`）
   ⇒ 不存在单一开关能停掉全部固化产物；停掉三个抽取器仍会生成摘要、仍会迁移原条目。
2. **无显式队列 / 水位**：SDD 画了 `consolidation.jsonl`（至少一次、幂等）与
   `fromSeq/toSeq` 水位、`consolidationId`。本仓没有该文件，也没有序列号。

勘察结论：第 2 点在本仓架构下**已由既有机制承担**，缺的是把它写成可验证的口径，而不是再造一份
权威：

- **持久队列 = L2 未迁移的 episodic 条目本身**（`memory.jsonl` 单一权威、原子写、跨进程合并）；
- **水位 = 会话成功提交后把该批条目迁 L4**（`_commit_summary`）。低于价值门、空摘要、截止越界、
  摘要器抛错时条目**留在 L2** ⇒ 下次节拍重试，即 SDD 的「超时保留水位，下次继续」；
- **幂等 = 稳定产物 id + 同载荷重放零副作用**（change `0306`／ADR-0296）。

因此本 change 只补**真正的缺口**（可关闭性），并把队列/水位口径钉成测试，避免以后误加第二权威。

## What Changes

- `MemoryStore(consolidation_enabled: bool = True)`：缺省 `True` ⇒ 与变更前逐字一致；
  `False` 时 `compact()` **立即返回 `None`**，不评分、不调用任何模型、不写摘要/派生条目、
  不迁移、不记效应。`forget()` 与滑窗中期摘要（`summarize_slice`）**不受影响**。
- 配置键 `memory.consolidation_mode`（`active` / `off`，缺省 `active`），三面齐备：
  CLI `--memory-consolidation-mode` / env `CORE_MEMORY_CONSOLIDATION_MODE` / yaml
  `memory.consolidation_mode`；组合根以 `consolidation_mode() != "off"` 注入 store。
  非 `off` 取值（含拼写错误）归一为 `active` —— 与 `memory` 段既有 kill-switch 同口径：
  方向恒为「保持变更前行为」，拼写错误不得静默停用固化。

## Non-goals

- **不新增 `consolidation.jsonl`**：会引入第二权威与双写一致性面；当前无多 worker / 跨进程
  消费者需要独立队列视图，L2 本身即可见、可重放。
- **不加条目序列号 / `consolidationId` / `extractorVersion`**：产物 id 已稳定、写入已幂等；
  版本记录需要同时给四路 prompt 建版本域，属独立设计（见 ADR 局限）。
- **不加失败退避 / 负缓存**：低价值会话每个节拍会重新评分（见 ADR 局限）；无实测成本证据前
  不引入新的重试状态机。
- 不改 `forget()`、滑窗中期摘要、会话转录。

## Impact

- 代码：`src/core/memory/store.py`（构造参 + `compact` 早返回）、
  `src/core/configuration/manager.py`（ConfigSpec + 访问器）、`src/core/runtime.py`（接线）。
- 行为：缺省路径逐字不变；显式 `off` 时固化四路全停、原情景保留在 L2。
- 规格：`memory` **ADDED** ×1、`configuration` **ADDED** ×1。
- 测试：新增 `tests/test_memory_consolidation_mode.py`（行为 + 配置三面 + 组合根接线 +
  队列/水位语义）。
