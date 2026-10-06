# Phase 28：上下文压缩 / 多流复用机制 + pet/beast 返回内容——四缺陷账本（E44 + E45 + E46 + E47）

> **定性**：本 Phase 承接两条机制 review（「memory 超过 context window 的压缩机制」是否 ready、「多流复用机制」是否完善）与一条新增关注点（pet/beast 任务完成/召回时主 Agent 能否查看返回内容）。
> 一手核实结论：**机制①＝「抢救 + 强制终止」，非「压缩续聊」**（`ctx.messages` 全程不截断，LLM 每轮收全量历史）；**机制②＝「复用同一条 TCP」并发场景不成立 + 记忆隔离单向**（主不读兽、兽可读主）；**pet/beast 返回内容＝死数据**（无工具查询、不落 L2、状态接口不含正文）。
> 上述各项均非规格违约（现有 spec 未明文要求「压缩续聊 / 双向隔离 / 结果可查 / 会话隔离」），故本 Phase 为**缺陷账本（登记）**，实施与否须视产品方向裁决。
> **第四项（E47）＋一条裁决**：承接「开不同 session 对话框时的多流复用」追问 —— 一手核实：复用点＝**共享一个 runtime + 一个 loop 实例**（`ui/api.py:105`；session 只是 `session_id` 标签，非 loop 实例），多流并发在环内**安全**（每轮自建 `ctx`，无 per-call 实例状态），但**检索面不按 session 过滤** ⇒ 会话之间互读记忆（登记 **E47**）。同批裁决：**E45 的 TCP 半条不列为缺陷** —— ADR-0064 的**有意取舍**（线程本地免锁）＋规格未要求「跨线程同一条 TCP」⇒ **不改**，登记为已知局限。

## 0. 结论总览

| 编号 | 缺陷 | 判死证据（行号） | 定性 | 修复方向 |
|---|---|---|---|---|
| E44 | 上下文压缩机制未 ready | `loop/default.py:365` `_should_compact` + `:377-399` `_compact`（persist/compact/forget 三步）全程**不截断 `ctx.messages`**；`loop/planner.py:120-128` `_build_request` 无窗口截断 | 「抢救 + 强制终止」非「压缩续聊」 | 若要求真压缩续聊：`_build_request` 前以摘要替换旧历史 |
| E45 | 多流复用「同一条 TCP」并发不成立 + 记忆隔离单向 | `llm_provider/http_pool.py:9-11/70-74` 连接池 `threading.local` 线程本地 + `stdlib_provider.py:147/172/186` 全走 `to_thread` 任意工作线程 ⇒ 并发不共享同一条连接；`runtime.py:564` 主 loop 排除 `beast.*` 而 `_beast_loop` 不排除主 loop 记忆 ⇒ 单向 | 复用仅单线程串行成立；隔离＝「主不读兽、兽可读主」 | TCP：**已裁决不改**（ADR-0064 有意取舍，登记已知局限）；隔离：双向排除或登记共享记忆设计 |
| E46 | pet/beast 任务完成/召回后返回内容死数据 | `beast/manager.py:74-76` result 存 `session.last_result` 但**零读取方**；`pet/core/session.py:146-147` `wake()` 存 `_last_trace_id` 后于 `:153` `return result`，而驱动侧 `driver.py:67` 丢弃返回值；`tools/` 无 beast/pet 工具、不落 L2、CLI 仅 print 状态（`_print_pet_status :1601`） | 主 Agent 无法查看返回内容（beast 真死 / pet 半死） | beast recall 前 `session.remember()` 落 L2 + status/tool 查询 `last_result`；pet 驱动侧接住返回值 + status 暴露最近结果正文 |
| E47 | **会话之间**记忆检索不隔离（附属：会话注册表丢更新） | `context/assembler.py:66-70` → `memory/store.py:95` `read(query, budget)` **只按 source 前缀过滤、无 session 过滤**（而 `loop/default.py:469-474` `remember()` 落库**是带 `session_id` 的**）；`ui/api.py:174-175` 的会话隔离是**调用方手写后置过滤**（只覆盖展示，未覆盖喂给 LLM 的检索）；`ui/sessions.py:33-40` `create` 读回→合并→写回**无锁** | 会话**不是**隔离边界：A 对话框沉淀的事实可进 B 的 system prompt（`planner._system_prompt` → `assembler.build`） | 复用既有过滤管线给 `read()` 补 session 维度（**不新造机制**）；`SessionRegistry` 加进程内锁（可独立修） |

## 1. 一手核实（证据）

### 1.1 E44 上下文压缩机制未 ready

| 证据点 | 位置 | 实况 |
|---|---|---|
| 压实触发 | `loop/default.py:365` `_should_compact` | 轮数 / token 阈值判定触发 |
| 压实动作 | `loop/default.py:377-399` `_compact` | 三步：`compactor.compact(ctx.messages)`（提炼沉淀）→ `memory.compact(...)`（记忆固化）→ `memory.forget(...)`（遗忘归档）；**全程不截断 / 不替换 `ctx.messages`** |
| 消息组装 | `loop/planner.py:120-128` `_build_request` | `messages = [Message(role="system", ...)] + 全量 _to_messages(ctx.messages)`，**无窗口截断 / 无摘要替换** |
| token 统计 | `loop/default.py:466` `observe` / `:409` `perceive` | `observe`：`ctx.token_used += len(str(result.data)) // 4`（**行动结果**）；`perceive`：`len(user_input) // 4`（**本轮输入**）。两处皆**累加**、皆不裁剪窗口 —— 全仓 `token_used` 仅两处消费（`:277` 预算终止、`:375` 压实判定） |
| 预算裁剪（易误读） | `context/budget.py:25` `BudgetManager.enforce` | 裁剪机制**存在**（必保项超预算抛 `BUDGET_EXCEEDED`；`_trim` 跳过放不下的项、不饥饿），但它裁的是**装配包的 `facts`（检索到的记忆）**，**不作用于 `ctx.messages` 对话历史** |
| 终止语义 | 主循环 | 压实后仍按既有轮数 / 预算条件终止（非「压缩后续聊」） |

**结论**：现有 `_compact` 是**记忆维护**（沉淀/固化/遗忘），不是**上下文压缩**。`ctx.messages` 全程不减少，LLM 每轮收到全量历史 ⇒ context window 超限时无法「压缩继续聊」，只能靠轮数/预算「强制终止」。准确口径是「**对话历史**无裁剪」，**非**「系统无预算裁剪」—— 预算裁剪在 `context/budget.py:25`，只作用于装配包的检索内容。

### 1.2 E45 多流复用（TCP 连接 + 记忆隔离）

| 证据点 | 位置 | 实况 |
|---|---|---|
| 连接池所有权 | `llm_provider/http_pool.py:9-11` + `:70-74` | `HTTPConnectionPool` 用 `threading.local()` **线程本地所有权**，不跨线程共享 |
| 调用线程模型 | `llm_provider/stdlib_provider.py:147`（chat）/ `:172`（embedding）/ `:186`（SSE） | 全经 `asyncio.to_thread(...)` / `run_in_executor(None, ...)` 落到默认线程池**任意工作线程** |
| 记忆隔离（主） | `runtime.py:564` | 主 loop 装配 `exclude_source_prefixes=("beast.",)` ⇒ 主 agent 检索排除 `beast.*`（全仓**仅此一处**启用排除，其余为 `memory/protocol.py:54`、`context/assembler.py:28`、`memory/store.py:95` 的管道参数） |
| 记忆隔离（兽） | `runtime.py` `_beast_loop` 装配段 | 兽 loop 注入 `source=beast.<agent_id>`，但**兽检索时不排除主 loop 记忆** |
| 返回主 agent | `runtime.py:752-760` `_dispatch`（`_delegate` 在 `:762-771`，`:727-738` 是 subagents 列表） | `result = await profile.loop.arun(task)` → `return {"ok": not result.failed, "reply": result.reply}` 回传 ✅（同步 delegate 路径正常） |

**结论**：
- **TCP**：并发场景下每次调用可能落不同工作线程 ⇒ **无法确定性复用同一条 TCP 连接**（仅单线程串行场景成立）。这**不是缺口而是取舍**：`http_pool` 在 change `0060`/`0066`（ADR-0064）**有意**选线程本地（免锁、无归还竞争），而规格「连接复用」场景只要求「复用底层 connection / keep-alive + 失效自动重建」，**未**要求「多流并发复用同一条 TCP」⇒ **已裁决：不改**，登记为已知局限（见 §3）。
- **隔离**：**单向**——主不读兽、兽可读主。符合「共享记忆」设计（兽需读主记忆获取上下文），但**不符合「相互隔离」字面要求**。

### 1.3 E46 pet/beast 返回内容死数据

| 证据点 | 位置 | 实况 |
|---|---|---|
| beast summon | `beast/manager.py:70-76` | `await handoff(...)` → result 存 `session.last_result`（L74）、`last_trace_id`（L75）→ `recall()`（L76） |
| beast 查询入口 | tools/ + entry.py | **无** beast/pet 查询工具（`tools/builtin.py` 零命中）；宠物状态呈现（`_pet_control :1574` / `_print_pet_status :1601-1607`）**不含任务正文**；`last_result` 全仓**仅 `beast/session.py:38` 定义 + `beast/manager.py:74` 写入、零读取方** ⇒ 主 Agent（经工具/L2/状态接口）**无查询入口** |
| pet wake | `pet/core/session.py:146-147`（返回 `:153`）+ `driver.py:67` | `result = loop.run(...)` → 存 `_last_trace_id`（trace_id **字符串**）→ **`:153` `return result` 把结果对象交还调用方**；丢弃发生在**驱动侧**（`driver.py:67` `session.wake()` 未接返回值；`driver.py:33` 注释自陈「返回 `LoopResult`，测试替身返回 `None`」）⇒ 结果对象止步于此 |
| pet 状态接口 | `pet/core/control.py` status L31-42 / snapshot | **不含任务正文** |
| pet 通知 | `pet/core/session.py:255-271` `_notify_owner` | 投递 report/surprise 通知，**非任务结果** |
| 正例对照 | `runtime.py:752-760` `_dispatch` | `await arun` → `return {"ok": ..., "reply": result.reply}` 正常回传（delegate 同步路径） |

**结论**：pet/beast 任务完成/召回后，返回内容（`result.reply`）对主 Agent 不可见（无工具查询、不落 L2、状态接口不含正文）⇒ **死数据**。与 delegate 路径的「reply 回传」形成对照。**两档强度不同**：beast **真死**（`last_result` 零读取方，跨进程亦无入口）；pet **半死**（结果对象本已交还调用方，止步于驱动侧丢弃；且 `surprise()` 路径会把 `result.reply` 拼进通知文本 `session.py:248-251`——但那是推送、不是「可查询」）。

### 1.4 E47 会话之间记忆检索不隔离（多流复用的正确性面）

**复用点先说清**（判据：复用发生在哪一层）：

| 层 | 复用形态 | 位置 |
|---|---|---|
| 进程 / 运行时 | 一个进程只建**一个** `Runtime`；`UIAPILayer` 持**一个** `DefaultLoop` 实例服务**所有** session | `ui/api.py:105` |
| 会话 | session **不是 loop**，是标签：`run_loop(session_id, …)` 透传给 `self._loop.astream(user_input, session_id=session_id)` | `ui/api.py:150` |
| 对话历史 | 服务端**不保留**：每轮 `perceive(user_input)` 只构造 `messages=[{"role":"user","content":user_input}]` 一条 ⇒ 多轮连贯靠前端回传 + L2 检索 | `loop/default.py:406-409` |
| HTTP 连接 | 线程本地 keep-alive：同线程连续调用复用同一条，跨线程不复用 | `http_pool.py:74` |

**并发安全性逐项**（共享一个 loop 实例的前提下）：

| 共享物 | 并发形态 | 判 |
|---|---|---|
| `DefaultLoop`（1 个服务全部） | 多协程（`/run` 是 `async def`，事件循环内交替） | ✅ 每轮自建 `ctx`，**无 per-call 实例状态** ⇒ 可重入 |
| `MemoryStore` L2 | 协程 + 线程池读 | ✅ `RLock`（`memory/backend.py:27`）；`entry.reuse_count += 1` 是共享对象就地自增（进程内强化）⇒ 计数叠加，无正确性影响 |
| `Tracer._events`（在途表） | 事件循环单线程 | ✅ 无锁但不跨线程；free-threaded 构建下才是隐患 |
| `EffectTracker` / `PluginRegistry` / `CoeffectResolver` | 线程池 | ✅ 各自 `RLock` |
| `HTTPConnectionPool` | `to_thread` 落工作线程 | ⚠️ 线程本地 ⇒ 并发即多条连接（E45-TCP，已裁决不改） |
| `SessionRegistry.create` | FastAPI **同步**端点跑在线程池（`add_api_route` 注册的是 `def`，Starlette 扔进 worker 线程） | ❌ 读回→合并→写回**无锁** ⇒ 两对话框**同时新建**会话可能**丢一个**（后写覆盖前写）；`write_state` 是原子写（tmp+`os.replace`）⇒ 不写坏文件，但「不写坏」≠「不丢」 |

**缺口**（本条目主体）：喂给 LLM 的**唯一**检索路径是 `assembler._gather_facts(task)` → `MemoryStore.read(query=任务文本, budget)`，过滤面**只有 source 前缀**（且只有主 loop 配了 `("beast.",)`）——**没有任何 session 过滤**。而 `remember()` 落 L2 **是带了 `session_id` 的** ⇒ **数据上有键，检索上不用键**。现存的三种「隔离」机制对比：

| 机制 | 谁在用 | 是否 session 边界 |
|---|---|---|
| `exclude_source_prefixes`（装配级 source 前缀） | 主 loop 排除 `beast.*` | ❌ 只能按 source |
| 调用方后置过滤（`e.session_id == session_id`） | `ui/api.py:174-175` `get_memory`（展示面） | ⚠️ 手工，且只覆盖展示，**不覆盖喂给 LLM 的检索** |
| `session_id` 过滤 | **无人**（检索路径未用） | — |

**症状**：对话框 A 聊出的事实会被检索进对话框 B 的 **system prompt**（`planner._system_prompt` → `assembler.build(self._task(ctx), stage="reason", budget=2048)`），只要相关度高。又因服务端不保留 per-session 历史（上表第三行），**会话连贯性的全部重量都压在检索上**，而检索这一层恰好不隔离。

## 2. E44 修复方向

- 若产品方向要求「压缩续聊」：在 `_build_request` 前对 `ctx.messages` 做摘要替换（保留 system + 压缩中间历史 + 尾部近窗），或在 `_compact` 里把旧历史替换为 compactor 产出的摘要 Message。
- 若维持「抢救 + 强制终止」现状：在契约 / spec 登记为**有意行为**（类同 phase-19 E6 的「压实启发式有意行为」订正），本缺陷销账。

## 3. E45 修复方向

- **TCP**：**已裁决（本次）：不改**。理由 —— ① ADR-0064 的**有意取舍**（线程本地 ⇒ 免锁、无归还竞争）；② 规格「连接复用」场景只要求「复用底层 connection / keep-alive + 失效自动重建」，**未**要求跨线程同一条 TCP；③ 改为「按 origin 单例池」要引入跨线程共享 `http.client` 与归还竞争，收益仅省几次握手。⇒ 登记为**已知局限（每工作线程一条连接）**，不列为缺陷。
- **隔离**：若要求「相互隔离」，给 `_beast_loop` 也注入 `exclude_source_prefixes=("loop",)`（排除主 loop 记忆）；若维持「共享记忆」设计，登记为设计现状。

## 4. E46 修复方向

- **beast**：`recall()` 前把 `last_result.reply` 经 `session.remember()` 落 L2 记忆（`source=beast.<agent_id>`，复用 phase-26 的 source 注入），并提供 status / tool 查询 `last_result`。
- **pet**：`PetSession.wake()` **已经** `return result`（`session.py:153`），缺口在**驱动侧丢弃**（`driver.py:67`）⇒ 修法为**驱动侧接住返回值**并在会话留一份（或在 `wake` 内自行留存一份），再由 `status` / `snapshot` 暴露最近任务结果正文。**不新造 wake 语义**（`PetControl.wake` 是另一个「恢复让行」动词，勿混）。

## 5. E47 修复方向

- **检索隔离（主体）**：**复用既有过滤管线** —— `MemoryStore.read()` 已有 `exclude_source_prefixes` 过滤面（在被排除项**排名与预算之前**剔除），按同型手法补一个 `session_id` 维度（或由 `DynamicAssembler` 透传当前会话），**不得新造第二套记忆检索**。配套需裁决：**会话是否就是隔离边界**（若「事实层跨会话共享」是有意设计，则应改为**显式登记**该语义，而非默认无过滤）。
- **注册表丢更新（附属，可独立修）**：`SessionRegistry.create` 的读回→合并→写回加进程内锁（或写回前 `exists` 复检）；这是**并发缺陷**、非能力缺口，**修它不需要先裁决会话隔离语义**。附带记一条潜在隐患：`write_state` 的临时文件名固定为 `<name>.tmp`，**同一 path 并发写**会交叉写同一 tmp（不同 path 各自独立，当前调用点互不重叠，故仅登记）。

## 6. 去重边界

- 不重复 E27/B2/C7/C8（phase-20 已列）/ observability/rag/skillhub（phase-22）/ 缺口③（phase-23）/ E30·E31·E32（phase-24）/ E33·E34·E35·E36（phase-25）/ E37·E38·E39（phase-26）/ E40·E41·E42·E43（phase-27）。
- E45-TCP 与 change `0060`/`0066`（ADR-0064「连接复用」）的关系已澄清：ADR-0064 落地「线程本地按 origin 复用 keep-alive」是**有意取舍**，规格只要求「复用连接 + 失效重建」、**未**要求「跨线程同一条 TCP」⇒ 该半条**不列为缺陷**（登记已知局限），无需与 ADR-0064 争边界。
- E46 与 phase-26（E37 神兽记忆命名空间断裂）**不重复**：phase-26 修的是「神兽轨迹混入主记忆污染」（写入侧 source + 读取侧排除），E46 指向「任务**返回内容**主 Agent 不可查」（结果可见性）。
- E47 与 E45 **不重复**：E45-隔离指向「主 loop 与神兽之间」（**source 命名空间**），E47 指向「**会话之间**」（`session_id`）——同属「检索面缺过滤」的同型症状，但边界不同。E47 与 phase-26（E37）亦不重复：E37 是**写入侧** source 注入 + 读取侧 source 排除（跨命名空间），E47 是**同一命名空间内**按会话切分。

## 7. 红线与裁决

- E44/E45/E46 均非规格违约，**不得以缺陷修复名义 `skip_specs` 强推**；若实施，须视产品方向裁决后**规格先行**。
- E45 若改「双向隔离」会破坏现有「共享记忆」设计（兽读主记忆获取上下文），须先裁决。
- E46 落 L2 须复用 phase-26 的 `source=beast.<agent_id>` 注入面，**不得新造 seal/recall API**（phase-26 已知局限口径）。
- **E47 同样是「现状非违约」**（规格未把会话定为隔离边界）⇒ 若实施，须先裁决「会话是否作为隔离边界」，再**规格先行**；修法上**复用既有过滤管线**（`read()` 已有 `exclude_source_prefixes` 过滤面，补 session 维度即可），**不得新造第二套记忆检索**。**注册表丢更新除外** —— 它是纯并发缺陷，可独立修、无需先裁决。
- **已裁决（本次）**：E45 的 TCP 半条**不列为缺陷**（ADR-0064 有意取舍），登记为已知局限。

## 8. 收口

- **四条**缺陷登记完毕，等待产品方向裁决（E44「压缩续聊 vs 有意行为」、E45「双向隔离 vs 共享记忆」、E46「结果可见性」、E47「会话是否作为隔离边界」）。
- 建议优先级：**E46 最高**（主 Agent 无法查看子任务结果是编排闭环的真实缺口，与 phase-17 委托语义直接相关）；**E47 并列次高**（多流复用是既定用法 —— 「开不同 session 对话框」即触发，而检索不隔离会把 A 的事实灌进 B 的 system prompt）；E44 次之；E45-隔离 视产品是否要「相互隔离」裁决。
- E47 附属的 `SessionRegistry` 丢更新可**先行独立修**（不等裁决）。
