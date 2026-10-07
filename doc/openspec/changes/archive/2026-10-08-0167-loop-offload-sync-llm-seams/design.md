# 0167 · 设计

## 1. 缺陷定位（为什么是「调用点」而不是「桥接」）

`LLMProvider` 的双入口是**刻意的**设计（`doc/03-interfaces/llm-provider-interface.md`）：
异步为主（`acompletion`），同步为**薄壳**（`completion` = `asyncio.run(acompletion)`）。薄壳的合法性
**建立在「调用方不在事件循环线程上」这一前提**上；`asyncio.run` 检测到运行中的循环即刻抛
`RuntimeError`（CPython 行为，非本仓选择）。

于是有两种修法：

| 修法 | 做法 | 评价 |
|---|---|---|
| **A（本 change 取）** | 在 **loop 边界**把含同步模型调用的整段工作卸载到工作线程 | ✅ 事件循环不被阻塞（LLM 往返在工作线程）；✅ DI 契约零变更；✅ 与 ADR-0064 ② 的既有前提一致；✅ 改动面＝**三个调用点** |
| B（否决） | 改 `_llm_text` / `completion` 让其在有循环时**另起线程跑**并**同步等待**结果 | ❌ 调用方仍在**事件循环线程**上**同步阻塞**等 LLM 网络往返（数秒）⇒ 把「必抛」换成「卡死」，UI 冻结；❌ 且对全部五处接缝统一改，而其中三处（SOP / 迭代 / 进化）从 CLI 一次性进程调用时**现状即正确** ⇒ 属投机改面 |
| C（否决） | 把 `summarizer` / `turn_observer` / `cold_path` 全部 async 化 | ❌ 触及 4 个 Protocol + 全部调用方（含 skills / evolution / memory 三包）⇒ 为**一个线程边界**付重构级代价；若将来确需 async 化，应先立 ADR |

**为什么 A 是安全的**（而不是「把线程当补丁」）：本仓的 LLM 传输层**本就为工作线程设计** ——
`http_pool.py:9-10` 声明「空闲连接存在 `threading.local()`，不跨线程共享」，ADR-0064 决策② 明文
「provider 的同步传输本就在工作线程上跑（`asyncio.to_thread` / `run_in_executor`），同一线程的连续调用即复用」。
同步接缝在工作线程上运行**不是绕过**，而是**回到设计前提**。

## 2. 三处边界（逐条：既有 / 改动）

| # | 站点（`src/core/loop/default.py`） | 现状 | 改动 | 该段内的模型调用 |
|---|---|---|---|---|
| ① | `:321` `self._compact(ctx, trace_id)` | 循环内同步调用 | `await asyncio.to_thread(self._compact, ctx, trace_id)` | `MemoryStore.compact()` → 摘要（`summarize_with`）+ 关键事实抽取（`extract_with`）+ 提升钩子（`summary_promoter` → `notes.promote_session_summary`，**无**模型调用） |
| ② | `:326` `self._notify_turn(ctx, trace_id, ok=…)` | 同上 | `await asyncio.to_thread(self._notify_turn, ctx, trace_id, ok=…)` | 注入的 `turn_observer` → `sop_extractor.observe`（SOP 提炼）/ `skill_iterator.decide|consider`（迭代）。**同闭包内**的 `skill_feedback.record_*` 与 `note_store.observe_turn` **无**模型调用（一起被卸载，代价是线程跳一次，可忽略） |
| ③ | `:335` `self._maintain(trace_id)` | 同上 | `await asyncio.to_thread(self._maintain, trace_id)` | 维护节拍：`memory.forget()`（无模型调用）+ `cold_path()` → `evolution_worker.maybe_run()`（review / patch author）。节拍状态 `_last_maintenance` 在工作线程写入 —— 单写者（同一个循环实例），无并发 |

**为什么不拆更细**（只卸载含模型调用的那一半）：拆分需要把 `on_turn` 闭包（组合根）或 `_maintain`
的两件事**从内部切开**，等于为了让「线程边界」精确而改动组合根与维护语义 —— 收益（省一次线程跳）远小于
代价（面变大、语义变复杂）。取「整段卸载」：边界清晰、语义零变化。

## 3. 三个私有方法**保持同步**

```python
def _compact(self, ctx: LoopContext, trace_id: str) -> None:   # 不变
def _notify_turn(self, ctx: LoopContext, trace_id: str, *, ok: bool) -> None:  # 不变
def _maintain(self, trace_id: str) -> None:                    # 不变
```

- 只有**调用点**变（`astream` 是 async generator，`await` 合法）；
- 直接调用它们的测试 / 既有代码**零影响**；
- 三处内部的 `try/except` 降级链**逐字不动** ⇒ 遥测事件名（`maintenance_failed` /
  `turn_observer_failed` / `cold_path_failed`）与文案零回归。

## 4. 语义边界（零回归清单）

| 面 | 约束 |
|---|---|
| 终止语义 | 不变（压实/维护不改变终止条件与回复内容） |
| 事件面 | `step_completed` / `loop_finished` / `loop_failed` 的**顺序与载荷**不变（卸载点是 `await`，序列化语义等价） |
| 降级链 | 不变（三处内部 catch 逐个保留） |
| 转录追加 | 不变（`remember` / `_append_transcript` 不在卸载面内） |
| 节拍状态 | `_last_maintenance` 语义不变（仍是「距上次维护的间隔」） |
| DI 契约 | **零变更**（四个接缝仍是同步 callable） |

## 5. 可观测的**增量**（本 change 的顺带收益）

卸载后，原本被吞掉的失败**仍会被吞**（降级链不变），但**不再发生**：压实的摘要与关键事实、
SOP 提炼、技能迭代、进化 review / patch 会**真的产出**。⇒ G3（`0153`）与 G4（`0155`）两条已收口能力
**首次在生产路径上生效**。

## 6. 局限（写进 ADR-0157 与 known-risk）

1. **交叉会话的并发写未加锁** —— 卸载期间事件循环可推进**其他会话**的 loop 任务；`MemoryStore` /
   `EffectTracker` 等共享状态**无锁**。该竞态**先于本 change 存在**（既有同步路径同样无锁，只是窗口更小），
   本 change **不引入也不消除**；消除需给 store 加锁或按会话分片（另议）。
2. **无超时 / 无取消** —— `to_thread` 不提供取消；工作线程里的模型调用卡住时，本轮收尾会**等它**。
   缓解面是 `LLMProvider` 既有超时/重试（`timeout_s`）与「失败降级」链（另议）。
3. **只覆盖三处已确认的边界** —— 若将来新增「循环内同步模型调用」的站点（新观察者 / 新维护步骤），
   需同样卸载；本条**无自动门禁**（测试只钉住当前三处）。
4. **线程跳一次的成本** —— 三处各一次 `to_thread`（~ms 级），相对其内部的模型往返（~s 级）可忽略，
   但**非零**；「不含模型调用」的收尾段（如 `memory.forget`）也被一并卸载。
5. **不改变 `completion()` 薄壳** —— 从**同步**上下文（CLI 一次性进程）调用它仍是既有语义；
   从**事件循环内**直接调用它仍是**错误用法**（本 change 只把 loop 侧的用法改对，未加防呆断言）。
