# 0167 · 收尾与维护中的同步模型调用：卸载出事件循环

> 触发：用户 2026-10-08 实测「执行 llm 回的 tool_id 执行信息，刚开始是好的，跑着跑着后面执行都突然无法正常执行」。
> 本 change 是与用户批准的三项修复并列的**第 3 项**（`先做1和3`），独立于 change `0166`（推理输出协议）。
> 证据：`~/.core/state/traces.jsonl` 的 `maintenance_failed` 记录。

## Why（事故与后果）

**现象**：trace 里 26 条 `maintenance_failed`，载荷逐字为
`"asyncio.run() cannot be called from a running event loop"`，分布在 6 轮，每轮计数 **1 / 1 / 8 / 2 / 3 / 11**；
每轮计数恰为 `max(0, rounds - 9)`，而 `Compactor.should_compact` 的门槛是 `_ROUND_THRESHOLD = 10`
⇒ **计数与压实触发完全吻合**（这是把 26 条归因到压实的定量依据，而非猜测）。

**调用链**（每一跳都已点到行号）：

```
astream 的轮循环（async，`default.py:254`）
  └─ default.py:321  self._compact(ctx, trace_id)          ← **在事件循环内同步调用**
       └─ memory/store.py:242  MemoryStore.compact()
            └─ memory/store.py:280  _summarize_sessions()
                 └─ memory/summarize.py:54  summarize_with(_llm_text)      # 会话摘要
                 └─ memory/extract.py        extract_with(_llm_text)       # 关键事实抽取（G4）
                      └─ runtime.py:366  _llm_text(prompt)
                           └─ llm_provider/provider.py:40  completion() = asyncio.run(acompletion(...))
                                ⇒ RuntimeError: asyncio.run() cannot be called from a running event loop
       └─ default.py:459  except Exception ⇒ self._trace(trace_id, "maintenance_failed", …)   ← **静默吞掉**
```

**根因**：组合根注入的 `_llm_text` 是**同步**接缝（`runtime.py:366`），内部走 `LLMProvider.completion()`
—— 后者的实现是 `asyncio.run(acompletion(...))`（`provider.py:40`，注释自述「同步薄壳：内部 asyncio.run 桥接」）。
**`asyncio.run` 在已有运行中事件循环的线程上必抛 `RuntimeError`**（CPython 明确禁止）。
而循环是**异步**主线（`astream`），却在轮内**同步**调用这条接缝 ⇒ **必抛** ⇒ 被既有降级 `except` 吞成一条遥测。

**后果（严重）**：**会话摘要（change `0153` / G3 半自动提升的**唯一输入**）与结构化关键事实抽取
（change `0155` / G4）在真实运行中从未成功过** —— G3 的越界判定依赖「既有摘要条目」、G4 的落库依赖抽取器
返回，二者输入恒空 ⇒ 两条已收口的能力**在生产上恒为空转**。压缩产物为空还意味着长会话的
「滚动摘要」实际只依赖 `context.Compactor` 的原文沉淀，memory 面的语义摘要始终缺席。

**同一缺陷类还覆盖另外两处**（同一根因、同一机制，故并入本 change，不另立）：

| 站点 | 触发面 | 被吞的产物 |
|---|---|---|
| `default.py:326` `_notify_turn(...)` | 注入的 `turn_observer`（组合根 `runtime.py:508` 的 `on_turn`） | ① `sop_extractor.observe` 达阈值时的 **SOP 提炼**（`skills/sop.py:98` `self._writer(...)`）；② `skill_iterator.consider/decide` 的**技能迭代**（`skills/iteration.py:113`），失败轮的迭代判据恒不产出 |
| `default.py:335` `_maintain(...)` | 注入的 `cold_path`（组合根 `runtime.py:661` `_cold_path` → `evolution_worker.maybe_run()`） | 进化面的 **review**（`runtime.py:642` `review_with(_llm_text)`）与 **patch author**（`runtime.py:676` `patch_author_with(_llm_text, …)`）—— 冷路径**达阈值即抛**，进化恒不产出制品 |

三处的失败**都被各自既有的 `except Exception` 降级**（`turn_observer_failed` / `cold_path_failed` /
`maintenance_failed`）⇒ 现象是「一切正常、只是什么都没产出」，操作者无从察觉。

## What Changes

**在 loop 的三处收尾/维护边界，把「可能含同步模型调用」的整段工作卸载到工作线程执行**：

```python
if self._should_compact(ctx):
    await asyncio.to_thread(self._compact, ctx, trace_id)        # 轮内压实（摘要 + 关键事实抽取）
...
await asyncio.to_thread(self._notify_turn, ctx, trace_id, ok=...)  # 收尾钩子（SOP 提炼 / 技能迭代）
...
await asyncio.to_thread(self._maintain, trace_id)                  # 维护节拍（含冷路径 → 进化）
```

- 三个私有方法的**签名与语义一字不改**（仍为同步函数，仍各自失败降级），改的只是**调用点**；
- **DI 契约零变更**：`turn_observer` / `cold_path` / `summarizer` / `key_fact_extractor` 仍是同步 callable
  —— 「同步接缝在**工作线程**上运行」正是本仓传输层的**既有设计前提**（ADR-0064 决策②明文：
  「provider 的同步传输本就在工作线程上跑（`asyncio.to_thread` / `run_in_executor`）」），`asyncio.to_thread`
  亦是与 `stdlib_provider.py:158` / `tools/builtin.py` 四处**同一惯用法**；
- **事件循环不再被阻塞**（这是安全修复的**必要条件**：修好后若仍在循环线程上跑，就会把「必抛」变成
  「卡死数秒」——把错误改成阻塞不是修复）。

## Non-goals

- **不改** `LLMProvider.completion()` 的桥接语义（`asyncio.run` 薄壳对其**既定使用场景**——无运行循环的
  同步上下文（CLI 一次性进程）——是正确的，本 change 不动它）；
- **不把**任何同步 DI 接缝改成异步（契约不动；若将来要 async 化，须先改各接缝的 Protocol 与全部调用方）；
- **不加**超时 / 取消语义（`to_thread` 不提供取消；工作线程中的模型调用超时属 `LLMProvider` 既有重试/超时面，另议）；
- **不做**其他「事件循环阻塞」面审计（本 change 只覆盖三处**已确认**含模型调用的收尾/维护边界）。

## Risks

- **线程安全**：被卸载的工作在**工作线程**上触碰共享对象（`MemoryStore` 内部状态 / `EffectTracker` /
  `NoteStore` / `SkillFeedback` / 会话转录）。此刻事件循环线程**挂起在该 await 上**，故同一轮内无并发写；
  但**其他会话的 loop 任务**（`arun` 可并发服务多会话）理论上可同时进入 —— 该竞态**先于本 change 存在**
  （既有同步路径同样无锁），本 change **不引入**新竞态，但在 ADR 记为已知局限。
- **线程池**：`asyncio.to_thread` 走默认 executor；三处每次至多一个在飞任务（`await` 串行）⇒ 无耗尽风险。
- **异常语义**：三处均在**方法内部**逐段 catch（`maintenance_failed` / `turn_observer_failed` /
  `cold_path_failed`），`to_thread` 层看不到异常 ⇒ 降级留痕与「不中断本轮」**逐字不变**。
- **可测性**：工作线程上**没有**运行中的事件循环 ⇒ 断言 `asyncio.get_running_loop()` 抛
  `RuntimeError` 即「已在工作线程」的**判别式**（本 change 的测试主判据）。
