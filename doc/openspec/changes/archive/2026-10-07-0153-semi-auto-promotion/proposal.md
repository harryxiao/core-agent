# 半自动提升（semi-auto promotion）· change 0153 · 记忆三面路线图 G3

## 为什么

0150（ADR-0142 / 账本 E94）已给出**显式**提升路径（`notes promote <session-id>`），并把
「由 loop 压实**自动**触发」**明文判为不做**（`notes` 规格 Scenario「不自动触发（设计裁决护栏）」）。
ADR-0142 局限① 同时**预登记**了自动提升的**唯一可辩护形态**：

> 只提升**跨过** `_MAX_SUMMARY_CHARS` 截断边界的会话 + 幂等覆盖 + **不自动 pin**。

本条即兑现该形态（路线图 **G3**，依赖 **G2** = 0151 已闭）。**可辩护的理由是信息论而非偏好**：

- 滚动合并的既有摘要**投喂时按 `_MAX_SUMMARY_CHARS = 2000` 取前 2000 字**（`summarize.build_prompt`）
  ⇒ 摘要**一旦越过该上界**，下一轮滚合并即**丢弃**上界之外的既有结论 —— **信息正在被不可逆销毁**。
- 此刻把**刚好完整的**摘要（首次越界的那一版，尚未被稀释）交付上层落 canonical 真相层，
  是**止损**：canonical 层无自动清理（ADR-0099），沉淀后**只读**、可回溯。
- 越界之后**不再重复交付**：后续摘要已是被截断的稀释版，覆写只会**劣化**已保存的完整内容。

⇒ 从「跑一轮压实就自动写盘」（不安全，会放大覆写面积）收窄为「**首次越界恰一次**」，
且**不自动 pin**（半自动产出是**普通** canonical 笔记：只经 Consult 命中面与 digest 注入，
**不**占常驻预算、**不**以硬约束身份逐轮进场）。这是对 0150 裁决的**最小、可辩护反转**。

## 改什么

**memory 侧交付「边界信号」**（一条注入式钩子，零 LLM、零三方依赖）：

- `summarize.py`：上界常量由 `_MAX_SUMMARY_CHARS` **公开为 `MAX_SUMMARY_CHARS`**（现为跨模块契约，
  不再私有）；新增注入契约 `SummaryPromoter = Callable[[str, MemoryEntry], object]`。
- `MemoryStore.__init__(..., summary_promoter=None)`（缺省 UNWIRED）。
- `_summarize_sessions`：在 `_commit_summary` **之后**，若该会话摘要**首次越过**上界
  （既有摘要长度 ≤ 上界「或无常驻摘要」而新摘要长度 > 上界）且 `session_id` 非空 ⇒
  取**本次产出的**摘要条目交付钩子**一次**；已越界 ⇒ 不再交付。钩子 UNWIRED ⇒ 不交付；
  钩子抛错 ⇒ **降级**（`warnings.warn` 留痕，不牵连压实的写回与迁移）。

**notes 侧接入**：

- `promote.py`：新增 `pin: bool = True` 形参 → `NoteEntry(pinned=pin)`；显式路径（CLI）缺省 `True`
  **逐字不变**；半自动路径传 `pin=False`。
- `runtime.py`：`NoteStore` 构造**上移**至 `MemoryStore` 之前；注入闭包
  `_promote_summary(session_id, summary) -> promote_session_summary(note_store, summary, session_id=session_id, pin=False)`。

### 设计原则（与架构同向）

- **memory 只报边界、notes 才落盘** —— 依赖方向 `notes → core.memory` 已存在（0150）；memory
  **不 import** notes（钩子注入），零新增反向依赖。
- **一次语义** —— 越界后不再交付，杜绝以稀释版覆写完整内容（与「幂等覆盖」正交：前者管**频次**，
  后者管**条数**）。
- **零回归** —— 钩子 UNWIRED 为缺省 ⇒ 既有全部 `MemoryStore(...)` 调用点（约 60 处）**逐字不变**。

## 规格

- `memory` **MODIFIED Requirement「记忆压实」**：追加**上界可见性 + 提升钩子**条款 + 3 Scenario
  （「摘要首次越过上界交付提升钩子一次」/「未越界或未注入钩子 ⇒ 不交付」/「提升钩子抛错降级不牵连压实」）。
- `notes` **MODIFIED Requirement「会话摘要提升（promotion）」**：触发面由「**仅**显式」扩为
  「显式 **或** 首次越界半自动」；`pinned=True` 收敛为**仅显式路径**（半自动 `pin=False`）；
  Scenario「不自动触发（设计裁决护栏）」**保留原场景名**、判据细化为「**未越过**滚动上界 ⇒ 不自动提升」，
  新增「首次越界 ⇒ 半自动提升且不自动 pin」与「已越界不再重复交付」。
- 其余 Requirement / Scenario **逐字不变**。

本项**非** `skip_specs`（行为变更、可见契约）⇒ 走规格先行、**不写** `.openspec.yaml`。

## 非目标（明确不做）

- **不**把「半自动产出置常驻」——半自动 `pin=False`（承 ADR-0142 局限① 明文）。
- **不**新增 `notes` 错误码；**不**接 `EffectTracker`（承 ADR-0099 canonical 层取舍）。
- **不**改 `_MAX_SUMMARY_CHARS` 的**数值**（2000）与节选**取前/取后**方向 —— 那是另一个面（ADR-0140）。
- **不**做 G1（pinned 预算判据）/ G4（结构化实体抽取）/ G5（rag 定位）——**不夹带**。
- **不**引三方库、**不**引 LLM 调用。

## 风险与红线

- **密钥红线**：钩子只搬运**已在 memory 内的摘要文本**到 canonical 层，不触密钥面、不读配置值。
- **零回归**：`tests/test_memory.py` / `test_notes*.py` / `test_loop.py` / `test_context_compaction.py`
  / `test_session_isolation.py` 既有用例逐字不动（除 `test_notes_loop.py` 那一条**护栏用例**按新契约改写）、全绿。
- **行为变更面**：仅当**注入钩子**且**首次越界**时新增 canonical 写入（缺省 UNWIRED ⇒ 零变化）。

## 影响面

改动 `src/core/memory/summarize.py`（常量公开 + `SummaryPromoter`）、`src/core/memory/store.py`
（钩子注入 + 交付）、`src/core/notes/promote.py`（`pin` 形参）、`src/core/runtime.py`（构造序 + 闭包）。
测试 `tests/test_memory_summary_promotion.py`（新增）、`tests/test_notes_loop.py`（护栏用例改写）、
`tests/test_notes_promote.py`（补 `pin=False`）。文档 `doc/02-modules/memory.md`、`doc/02-modules/notes.md`、
`doc/03-interfaces/memory-interface.md`、`doc/03-interfaces/notes-interface.md`、
`doc/04-testing/test-cases.md`（新 `## 69.`）、`doc/01-architecture/adr.md`（ADR-0145）、
`coding-plan/known-risk.md`。
