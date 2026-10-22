# Proposal — 0304 召回多样性与注入统计

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §6.4 / A8：

1. **召回无多样性控制** —— `MemoryStore.read()` 排序后直接按预算截断：同一会话的条目可无限霸榜，
   内容完全相同的条目各占一份预算（`content_hash` 已在 `0303` 落地，具备近重复判据）。
2. **调用方拿不到注入统计** —— 返回值只有条目列表，无法知道候选多少、被预算裁掉多少、
   要再多注入一条需要多少预算（A8「统计准确」不满足）。

## What Changes

- `MemoryStore.recall(...)` 返回 `RecallResult`：条目 + `matched_count` / `injected_count` /
  `excluded_by_budget` / `excluded_by_diversity` / `minimum_budget`；`read()` 委托并只返回条目
  （签名与返回值不变）。
- 检索管线在**排名之后、预算之前**加入两道多样性过滤（被滤项不吃预算、不被复用强化）：
  - 近重复抑制：`content_hash` 相同只留排名最高的一条（正文空白不参与；旧行哈希为空时现算）；
  - 同会话上限：`session_id` 非空的条目每会话最多 3 条（全局条目 `session_id=""` 不受限；
    调用方已用 `session_id` 参数收窄到单会话时不施加，避免截断该会话自身的事实面）。
- 统计口径：`matched_count` = 进入排名的候选数；`injected_count` = 实际返回数；
  `excluded_by_budget` / `excluded_by_diversity` 分别为预算与多样性剔除数；
  `minimum_budget` = 再注入第一条被预算裁掉条目所需的最小预算（无 ⇒ 0）。

## Non-goals

- **kind 配额（semantic/procedural/episodic 0.4/0.4/0.2）**：本仓 `MemoryEntry.kind` 只有
  `episodic` / `semantic`，无 procedural；技能条目（L3）已在 `0302` 退出事实面 ⇒ 无配额对象。
- **`maxPerSource=2`**：本仓 `source` 是粗粒度管道标签（`loop` / `extraction` / `compaction` /
  `episodic` / `transcript`），按它限 2 条会把关键事实（全部 `extraction`）压到 2 条 —— 与语义
  相悖。SDD 的「同一 run / 工具 / 技能」在本仓没有对应字段。
- 召回条数上限 8 / 硬上限 20、每条约 500 字符：当前以 token 预算为唯一上界，不叠加条数上限。
- `why` 明细、confidence/feedback 打分、CLI `memory stats`（P2-2 范围）。
- 不改 `_truncate` 的既有语义（首条无条件保留、超预算条目只跳过自身）。

## Impact

- 代码：`src/core/memory/protocol.py`（`RecallResult` / `recall` 协议）、`src/core/memory/store.py`
  （管线与统计）。
- 行为：同会话 >3 条、或存在完全同文条目时，`read()` 返回集合会变小（预期缺陷修复）。
- 规格：`memory` **ADDED** ×1。
- 测试：新增 `tests/test_memory_recall_diversity.py`；既有检索测试按新语义复核。
