# Design 0192 — 轮内压实会话化 + trace 会话键 + 诚实化

## 1. 问题定位（P3：缺陷定位到具体插件）

| 面 | 事实 | 缺口 |
|---|---|---|
| `loop/default.py:668` | `_compact` 裸调 `self._memory.compact()` | 空 `session_id` ⇒ 全量聚合（跨会话串扰） |
| `loop/default.py:584` | `_maintain` 传 `session_id=session_id` | 同循环两套口径 |
| `memory/store.py:422-423` | 契约注「空=全量……供**循环内节拍压实**使用」 | justification 失真（节拍其实传 session） |
| `context/compactor.py:102/:116` | `trace_id="compaction"`（常量） | 回滚归因过粗、不与会话其他压实共组 |
| `loop/default.py:651` / `compactor.py:45` | docstring 称「**多轮历史**提炼」 | 实输入 `ctx.messages` 仅本轮（文案撒谎） |

## 2. 设计决策

### 2.1 轮内压实一律会话化（只改调用面，不改全量实现）

`_compact` 第 668 行由 `self._memory.compact()` 改 `self._memory.compact(session_id=ctx.session_id)`。

- **空会话轮行为逐字不变**：`ctx.session_id == ""` 时 `compact(session_id="")` ≡ 裸调 `compact()`
  （store 的空串语义 = 全量），故 `test_loop.py:583`（无会话的既有压实测试）**不受影响**。
- **全量语义保留给显式调用**：`MemoryStore.compact` 的空串全量实现**逐字不动**；改变的是
  **循环内路径不再走全量**。契约注同步订正（`:422-423` 的「供循环内节拍压实使用」→
  「供**显式调用**（CLI / 运维命令面）」）。
- **为何不改 `_maintain`**：它**本已**会话化（`:584`），本条只是让 `_compact` 对齐它 ——
  「同一循环两条路径口径相反」正是被修的缺陷。

### 2.2 persist trace 会话键化

`key = session_id or "default"`（compactor 内 `key` 已在 `:92` 算出，供 id 使用）⇒ persist 两处
`trace_id="compaction"` 改 `trace_id=f"compaction.{key}"`。

- **与 store 既有口径一致**：`store.py:670`（会话摘要）/`:773`（关键事实）/`:486`（中期摘要）/
  `:631`（重要度写回）**恒**用 `f"compaction.{key}"`；persist 的常量是唯一离群者。
- **回滚归因细化（P3）**：按 `compaction.<sid>` 回滚即撤销**该会话**的压实产物，不再一次跨会话；
  且与同会话的会话摘要 / 关键事实**共组**（一次回滚整批撤销同一压实波次）。
- **time-travel 消费面核对**：撤销集取自检查点快照 `state["trace_ids"]`（`entry.py:865` /
  `manager.py:147`），是**运行期遇到的 trace id 列表**，不硬编码 `"compaction"` ⇒ **无消费面被打破**。
  全仓亦**无测试断言** persist 的 `trace_id == "compaction"`（断言的是条目 **id** 与 store 侧 trace）。

### 2.3 诚实化（沿 `0182` 先例）

- `_compact` docstring：（旧）「压实：多轮历史提炼沉淀」→（新）「压实：**本轮**消息 + 工具 I/O
  提炼沉淀（持久化产物 + 记忆固化 + 遗忘归档）；**多轮历史**由**三层滑窗**（change 0178）与
  记忆压实承载 —— 本方法不折入历史」。
- `ContextCompactor.compact` docstring：同口径（输入是**本轮** `history` 形参 —— 调用点传
  `ctx.messages`，**仅本轮**；`protocol.py:54` 明禁折入多轮 history）。
- **provenance 死面只注记不活化**：`compact` 读 `entry.get("id", "")` 产 `source_ids`
  → `persist` 写 `from:<id>` tag；但 `ctx.messages` 条目**无 `id`**（`{"role","content"}`）
  ⇒ 循环内 `source_ids` 恒空、`from:<id>` 恒不触发（仅测试以手造 `{"id":…}` 激活）。
  **注记**该事实（docstring 一句），**不**扩输入面（扩面 = 多轮 token 成本 + 去重新决策，Non-goal）。

## 3. 规格落点

- `memory`「记忆压实」：归约范围条款 —— 空串全量**保留给显式调用**；**循环内路径**一律会话化。
- `loop`「执行循环」：轮内压实的**记忆固化步骤**按本轮会话收窄（与维护节拍①同口径）。
- `context`「上下文自动压实」：产物 `trace_id` 携带会话键（与记忆侧其他压实 trace 同口径）。

## 4. 验证

- 红测试：他会话条目不被本轮聚合；trace 会话键；空会话回归；文案断言。
- 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`。
- `openspec validate` → 手工归档（0 行丢失 / 0 Scenario 标题丢失）。
