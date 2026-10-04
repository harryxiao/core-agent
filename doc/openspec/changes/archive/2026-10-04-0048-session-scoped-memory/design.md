# Design: 会话标识透传至记忆沉淀

## 决策 1：标识的传递方式 —— 调用参数（局部变量），而非循环实例状态

**取舍**：
- **A（`self._session_id` 实例态）**：`astream` 是长驻协程，同一 `DefaultLoop` 实例被
  `UIAPILayer` 共享；并发服务两个会话时实例态会**串号**（A 会话的沉淀落 B 会话名下），
  且需要额外的生命周期钩子清理。**否决**。
- **B（调用参数，本变更）**：`session_id` 作为三入口的可选 keyword 参数，在 `astream` 内是
  局部变量，逐轮传到 `remember`。并发天然隔离，无需实例状态与清理。**采用**。

**兼容性**：缺省 `""`——既有调用点（CLI 入口、测试、编排）零改动，语义与今天一致
（空串 = 未归属会话分组，压实/固化沿用 `""` 分组，不破坏既有数据）。

## 决策 2：读侧过滤位置 —— UI 层按 `entry.session_id` 过滤，不改 `MemoryStore.read`

`get_memory(session_id)` 当前把会话 ID 当检索 query 用。修法取舍：
- **A（给 `read` 加 `session_id` 过滤参数）**：动 L2 检索契约（`memory-interface.md:13`），
  需要改 `MemoryStore`/`MemoryBackend` 两处签名与全部实现，波及面远超本账本条目。**不做**。
- **B（UI 层过滤，本变更）**：`read` 仍按 query 取候选（query 传会话标识，得到一个候选集），
  UI 层再 `[e for e in entries if e.session_id == session_id]`。检索契约不动，改动最小且
  可测。**采用**。

**语义说明**：过滤后「未归属（空串）」条目不再出现在会话视图——这正是本次要修的口径
（会话视图只呈现本会话归属）。全局/未归属条目的检索仍由装配器（task-keyed 召回）覆盖，不受影响。

## 决策 3：`compact` 接线 —— UI 直调 `MemoryStore.compact`，并给 Protocol 补声明

真实压实早已在存储层实现（`memory/store.py:166`，接口文档 `memory-interface.md:107`
定义了会话聚合语义），只是 (a) UI 层是 no-op，(b) `MemoryStore` Protocol 没声明它。

- **扩展 Protocol 声明 `compact`**（而非 `getattr` 能力探测）：压实是记忆的**规格内能力**
  （`memory/spec.md` 「记忆压实」），接口文档已定义；Protocol 漏声明是契约缺口，补齐后
  pyright 能在编译期保证注入面具备该能力，避免"接了个没有 compact 的 store 再静默降级"。
- UI 传 `query=session_id` 限定候选范围；未注入 `summarizer` 时 store 内部只评分不写，
  属既有降级语义，UI 不额外分支。

## 决策 4：归组口径不变

压实/固化/遗忘的「按 `session_id` 聚合」算法与阈值一律不动（`memory/spec.md:68-71`、
`:108-111`）。本变更只让**写入侧**真正写入该字段——既有实现、既有测试、既有归档语义
（`compaction.<session_id>` 可撤销）全部复用。

## 风险与缓解

- **UI 既有断言变化**：`get_memory` 返回范围收窄 → `tests/test_ui.py` 相关用例同步为
  「写入带会话标识的条目后可见、跨会话不可见」（tasks 2.2 覆盖）。
- **测试替身**：注入 UI 的假 memory 若不实现 `compact`，Protocol 收紧后 pyright 会报 →
  测试替身补齐 `compact`（tasks 3.3 一并改）。
- **并发**：标识为调用局部变量，`astream` 并发调用互不影响（决策 1）。
