# Proposal 0211 — session_chain 读侧进只读诊断面

## 为什么

`MemoryStore.session_chain`（`memory/store.py:498-531`）是 change `0202`／ADR-0192 立的**零效应只读**口
（按 `ts` 主序重建某会话的情景链，节点携带 `entry_id / trace_id / ts / failed / after`），规格
`memory/spec.md:769`「情景链（时序相邻标注）」把 (f) 只读链重建写成了**行为规格** —— 但全仓
**零生产消费者**：`session_chain` 只被自己的单测调用。

这是六能力走查中「有规格无接线」死代码的一支：**情景链的写侧（`after:` 标注）通了、读侧不通** ——
链只在测试里可读，运维面（TUI 只读命令族 / CLI 诊断源）看不到「哪些轮失败、链条怎么接的」。

## 做什么

- **`core.diagnostics`（0162）加一张列表视图** `render_chain(deps)`（`views.py`）：与
  `render_sessions` / `render_notes` **同形**（`_sealed` 包裹 ⇒ 空店 `（空）`、读取异常降级一行、
  **视图不抛**），按**会话分组**列出最近若干节的链路语义。
- **`Deps` 加可选句柄** `chain: Callable[[str], list[ChainNode]] | None`（callable 注入先例 =
  `SessionsHandle`，`deps.py:30`）：诊断包**不引 `core.runtime` / `core.ui`**（硬红线，
  `test_runtime_is_sole_composition_root`），也**不自建** store 实例。
- **`entry._diag_deps`（:540-570）注入裸店**：`MemoryStore(backend=FileBackend(_state_path(
  "memory.jsonl")))` —— 先例 = `_memory_summary`（`:1632-1637`，同一路径助手、同一裸构造）；
  免 runtime 是刻意的（「配置坏了」是最该跑诊断的场景，见 ADR-0153 决策①）。`session_chain` 是
  **零效应只读**（`_all_entries()` 而非 `read()` ⇒ 不强化 `reuse_count`、不记任何效应）⇒ 诊断面
  「不产生副作用」的红线保持。
- **TUI `/chain`**（`ui/repl.py` 只读命令块 `:274-281`）：`_Command("/chain", "情景链（按时序）",
  handler="_show_chain")` ⇒ 复用**同一条** `_readonly_report` 接缝（0163 立的直分发路径），
  与 CLI 侧**同一份**产出。

## 不做（边界）

- **不改 `ChainNode`**：节点契约（`0202`）刻意**不含正文**（「本类不得成为第二条注入通道」）——
  本 change 只在**呈现侧**追加一张视图，`memory` 包**零改动**。
- **不给 `/chain` 加参数**：只读命令族（0163）的 `handler` 直分发**无参数面**（`arg=""`）；
  按会话细看由未来的**带参**命令承载，不在本 change。
- **不新增配置键**：视图是纯只读呈现，无行为开关；`Deps` 缺句柄即 `未接线`（同其余六张视图）。
