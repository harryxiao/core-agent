# 设计 — 记忆面 → 诊断面桥（change 0188 / ADR-0179 / 台账 E125）

## D1 缺口：失败摘要「已沉淀、无人读」

`loop` 侧已把轮级失败另立为 L2 条目 `loop.failure.<trace_id>`（`default.py:833-846`），
但 `Diagnoser.diagnose` 的输入只有 `Trace`（`success` / `plugin_id`）——**归因线索是结构化的**，
叙述性失败摘要进不了诊断面。`src/core/evolution/` 对 memory **只写不读**，故这是**结构性缺口**，
不是缺一句文案。

## D2 依赖倒置：注入 reader，不 import memory

`Diagnoser.__init__` 增可选 `failure_lookup: Callable[[str], str | None] | None = None`。

- 与 `summarize_with(llm)` / `extract_with(llm)`（memory 侧）/ `review_with(llm)`（evolution 侧）
  **同一「接缝注入」纪律**：单元**不** import 另一端的能力包，由组合根（L5）注入具体实现。
- 方向说明：`evolution → memory` 在 ADR-0045 下**本就允许**，且 `EvolutionEngine` 已持有
  `memory=backend` ⇒ 本 change **不是**为了绕过方向限制才注入；**而是**因为 `Diagnoser` 是
  **纯归因单元**（无状态、可单测、其构造面即其契约）——把 `MemoryBackend` 塞进它会**扩大其
  依赖面**并使其单测必须造后端。注入一个 `Callable` 把「取回失败摘要」的**具体机制**留在组合根。

## D3 落点：**新增可选字段**，不动 `issue`

`DiagnosisReport` 增 `failure_notes: list[str] = field(default_factory=list[str])`。

- **为什么不改 `issue`**：`issue` 是**判定叙述**（「缺陷归因于插件 X」/「多插件并列…」），
  且 `Proposer.propose` 把它原样带进候选 `delta={"issue": …}` ⇒ 往 `issue` 追加摘要会
  **改变既有字段语义**并**改动候选载荷**（本 change 的范围外）。新增字段则：既有构造、
  既有 `==` 比较、既有消费面（`proposer` / `engine`）**逐字不变**。
- **有界**：每条**失败** trace 至多取回一条；单条截断至 `_MAX_NOTE_CHARS`(400)；总数封顶
  `_MAX_FAILURE_NOTES`(3)（超出即停取 —— 截断比丢弃**先到者**更可预期：保留**最早**的失败证据）。
- 摘要为空 / `None` / 纯空白 ⇒ **不**入列（不留空串占位）。

## D4 fail-open：查询抛错 ⇒ 降级，不牵连判定

lookup 抛任意异常 ⇒ 吞掉（该 trace 无 note），诊断**照常**产出 —— 与既有降级纪律同型
（embedder 抛错降级词法、摘要器不可用降级省略）。缺省 `None`（UNWIRED）⇒ `failure_notes` 恒空、
`diagnose` 与既往**逐字一致**（回归锚）。

## D5 组合根接线：走 `MemoryBackend.search("")`，**不**走 `MemoryStore.read`

`runtime.py` 注入闭包：在 `backend.search("")` 的结果里按 **id 精确**取
`loop.failure.<trace_id>` 的 `content`。

- **为什么不用 `memory.read`**：`read` 是**语义检索**（相关性排序 + 预算 + **复用强化**）——
  change `0187` 后它还有**写副作用**。用一条**精确 id 查询**去驱动诊断，语义上就不该走检索面，
  更不该借道产生副作用。`search("")` 无查询词 ⇒ 纯枚举、**零写入零效应**。
- **为什么按 id 而非 source/前缀**：`loop.failure.<trace_id>` 是 `loop` 侧的**显式 id 约定**
  （`default.py:837`），比「按 tag 过滤再取第一条」更精确（同 trace 还可能有轨迹条目
  `loop.<trace_id>`、步序条目 `loop.steps.<trace_id>`，三者 `source` **同为** `"loop"` —— 见 0186）。
- **层无关**：按 id 枚举整个后端 ⇒ 条目被 `forget` 迁 L4 后**仍可读**（失败证据不应因归档而
  从诊断面消失；L4 只是层级，不是墓碑）。

## 不做（显式）

- **不**把 `failure_notes` 并入候选 `delta`（`Proposer` 只取 `issue`）—— 该消费面另议。
- **不**改归因算法（证据恒优先、先验只破并列）与 `engine._diagnose` 的**显式目标**路径
  （该路径不构造 `Diagnoser`，故不受本 change 影响）。
- **不**为 `Diagnoser` 加 memory 依赖、**不**加配置键（接缝由组合根硬接线，同 `review_with`）。

## 不变量

| 编号 | 不变量 |
|---|---|
| I1 | 未接线（`failure_lookup=None`）⇒ 报告与既往**逐字一致**（`failure_notes == []`） |
| I2 | `target_plugin` / `confidence` / `evidence` / `issue` 的判定**逐字不变**（桥只增补字段） |
| I3 | 查询抛错 ⇒ 降级（该 trace 无 note），诊断不中断 |
| I4 | 只查**失败** trace（成功 trace 的 lookup **不被调用**） |
| I5 | 零写入、零效应（lookup 走 `search("")`，不经 `MemoryStore.read`） |
| I6 | `evolution` 不新增 import 方向；`memory` / `context` 零改动；无新依赖、无新配置键 |

## 测试设计

| 用例 | 断言 |
|---|---|
| 未接线逐字不变（回归锚） | `Diagnoser()` ⇒ `failure_notes == []`，且 `== DiagnosisReport(..., failure_notes=[])` |
| 注入后含摘要 | lookup 对失败 trace 返回摘要 ⇒ `failure_notes == [摘要]`（顺序 = 失败 trace 顺序） |
| 查询抛错降级 | lookup 抛 `RuntimeError` ⇒ 归因 / `confidence` 与未接线**一致**、`failure_notes == []` |
| 有界 | 超长摘要 ⇒ 截断至上限；失败 trace 数超上限 ⇒ 只取前 N 条；**成功** trace 的 lookup 不被调用（spy 记录入参） |
| 组合根接线 | `build_runtime(...)` ⇒ `engine._diagnoser._failure_lookup is not None`；对后端中已沉淀的 `loop.failure.<id>` 取回正文（端到端） |
