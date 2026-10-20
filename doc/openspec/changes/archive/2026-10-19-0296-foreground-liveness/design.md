# Design — 0296 前台轮不被后台收尾与压实拖死

## 1. 生命周期改造

### 1.1 现状

```
轮 N：perceive → ReAct → loop_finished → schedule(post_turn)
轮 N+1：loop_started → await post_turn（最多数分钟）→ perceive → ...
arun：collect_result → await post_turn（无上限）
```

`_await_post_turn` 同时承担两件事：① 避免新一轮读写与旧轮收尾并发；② 让 `run()/arun()`
的「完成后收尾」语义成立。交互端 `astream` 并不需要 ① 的强串行，却为此付出了全部延迟。

### 1.2 新形态

```
轮 N：loop_finished → schedule(post_turn_N)
轮 N+1：loop_started → [上一轮仍在跑 ⇒ trace post_turn_overlap] → perceive → ...
post_turn_N → post_turn_N+1 → ...（后台单链路）
arun：等待本链末端，最多 post_turn_wait_timeout（缺省 120s）
```

- **前台不等待**：删除 `_astream_events` 中的 `await self._await_post_turn()`。
- **后台串行**：`_schedule_post_turn` 捕获当时的 `self._post_turn_task` 作为 `previous`；
  新 task 先 `await asyncio.shield(previous)`（仅同一事件循环、未完成时），再执行本轮收尾。
  这样旧轮收尾与新一轮收尾不重叠，又不会阻塞前台。
- **有界等待**：`_await_post_turn(timeout=...)` 用 `asyncio.wait_for`；超时取消该 task
  （其 `to_thread` 中的同步调用无法强杀，但事件循环不再等待），返回 `False`，
  `arun` 记 `post_turn_timeout` 后正常返回本轮 `LoopResult`。
- 后台链不会因为某一轮超时无限增长：每次 `_schedule_post_turn` 只保留一个「链末端」引用；
  链上每个 job 的模型调用与维护步骤各自有界。

### 1.3 并发后果与防护

前台与后台现在会并发触碰共享状态。逐项评估：

| 共享对象 | 既有线程安全 | 本轮处理 |
|---|---|---|
| `FileBackend` | `threading.RLock` | 不变 |
| `EffectTracker` | `threading.RLock` | 不变 |
| `SopExtractor` / `CandidateStore` | `threading.RLock` | 不变 |
| `MemoryStore._hot` / `_all_entries` | 单次 C 级 dict 操作 + 快照式 `update` | 不新增全局锁（避免长 LLM 期间锁死前台） |
| `SkillLibrary` | **无锁** | 新增 `RLock`（注册/查询/启停/持久化/索引） |
| `NoteStore` canonical | 后台不写 canonical（只写候选） | 不变 |

`MemoryStore` 的压实是「快照 → 模型调用 → 写回」，与前台写入交错时最多产生「摘要未包含
刚写入的一条」的**最终一致**偏差，不会丢条目、不会崩溃；以可靠性换前台可用性是本 change
的明确取舍。

## 2. 协作式截止时间

### 2.1 契约

`MemoryStore.compact(query="", budget=4096, *, session_id="", deadline=None)`：

- `deadline: float | None`，取 `time.monotonic()` 语义（`MemoryStore` 新增可注入 `clock`，
  缺省 `time.monotonic`）。
- 检查点是**模型调用之前**：`_score_importance` 的每条、`_summarize_sessions` 的每个会话
  摘要之前、三类派生抽取之前。
- 截止后：`warnings.warn`（只报会话键/阶段，不回显正文）并停止后续模型调用；已完成的
  会话写回保留（渐进式），**不**在截止后提交新的摘要。
- 不抛异常（与「压实失败降级」一致），由调用方的耗时事件归因。

### 2.2 single-flight

`MemoryStore` 新增 `threading.Lock`（非阻塞）：

- `compact` 开头 `acquire(blocking=False)`；失败 ⇒ `warnings.warn("compaction already running; skipped")`
  并返回 `None`，零模型调用。
- `finally` 释放。超时的工作线程在下一次检查点退出后会释放；此期间新触发只跳过，不排队。

### 2.3 调用方

- 轮内 `_compact_bounded`：`deadline = now + compact_timeout`，与 `asyncio.wait_for` 同值；
  工作线程收到同一截止时间。`compact_timeout` 缺省从 `120s` 调整为 `60s`，可由
  `loop.compact_timeout` 覆盖。
- `_maintain`：`deadline = clock() + maintenance_timeout`（缺省 120s，构造注入）。
  `run(name, step)` 在每步前检查；截止 ⇒ 记 `maintenance_failed`
  `{"step": name, "error": "deadline_exceeded"}`，跳过该步与后续步骤；`maintenance` 成本事件
  只包含已执行步骤。
- CLI `memory maintain --timeout S`：`deadline = time.monotonic() + S`，传给 `compact`；
  `forget` 前检查一次；截止则打印「已达到时间上限（部分步骤已跳过）」。

## 3. 后台模型调用上限

组合根新增独立 `background_llm = StdlibLLMProvider(..., timeout=background_timeout,
max_retries=background_max_retries)`，仅 `_llm_text` 使用（摘要、关键事实、关系、情景归纳、
SOP、Sedimenter、进化 review/patch）。主 `llm` 与 `LLMVerifier` 不变。

- 缺省 `60.0s / 0`：单次后台调用最多一次 60s 等待，不再有 3 次退避放大约 4 分钟。
- 用户可单独调大；设为 `(60, 0)` 时后台调用与既有单次超时一致，但**重试**从 3 降为 0
  （这是本 change 的唯一缺省行为变化，理由见 ADR）。
- 后台任务的重试语义改为「下一轮再试」：收尾失败仍只降级留痕，记忆/候选在后续轮次再处理。

## 4. 配置

| 键 | 缺省 | 校验 | 注入点 |
|---|---|---|---|
| `llm.background_timeout` | `60.0` | `> 0` 数值（布尔/非数值/≤0 阻断） | 后台 provider |
| `llm.background_max_retries` | `0` | `≥ 0` 整数（布尔/小数/负/非数值阻断） | 后台 provider |
| `loop.compact_timeout` | `60.0` | `> 0` 数值（布尔/非数值/≤0 阻断） | 四个 `DefaultLoop` |

三键均经 ConfigSpec 单一真源生成 CLI flag / env / yaml 三面，优先级链不变。

## 5. 被拒方案

- **保留串行、仅缩短超时**：上一轮收尾只要有一次 60s 调用，下一轮仍被拖住；无法覆盖
  `stop` 熵增。
- **前台完全不等 + 不串行后台**：多轮收尾并发写记忆/技能，放大竞态与模型调用；不取。
- **强杀工作线程**：Python 不支持；`to_thread` 无法终止。协作式检查点是唯一可靠边界。
- **把收尾放进独立进程/队列**：超出 P0，且引入跨进程状态一致性问题。
- **缺省关闭 Sedimenter**：会回退 0295 的沉淀质量改造；本 change 选择限制单次调用成本，
  不关闭能力。

## 6. 局限（登记 known-risk）

1. 截止只阻止**新**调用；已发出的 HTTP 调用仍受 provider 单次超时约束（缺省后台 60s）。
2. 超时工作线程可能在前台继续时完成剩余写回；与前台写入为最终一致，不保证摘要包含
   并发写入的最新条目。
3. CLI `memory maintain --timeout` 对实现了 `compact(deadline=...)` 的 store 生效；
   第三方/测试替身若忽略该参数，仍可能超出 CLI 期望（本仓实现已遵守）。
4. 后台链在极端情况下可滞后多轮（前台永不等待），顺序保序但非实时。
