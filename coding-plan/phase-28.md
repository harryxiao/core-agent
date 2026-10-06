# Phase 28：上下文压缩 / 多流复用机制 + pet/beast 返回内容——缺陷账本（E44 + E45 + E46 + E47 + E48 + E49；**已全闭**）

> **状态**：✅ **全闭（2026-10-06）** —— E46（0113/ADR-0106）、E47 主体 + 附属（0114/ADR-0107，附属随 `0115` 顺带闭合）、E49（B1 `0115`/ADR-0108 ＋ B2 `0116`/ADR-0109）、**E48 / E44 / E45-隔离（Phase 30 收口，`0117`/ADR-0110）**：E48-b **修** / E48-a **销账** / E44 **销账** / E45-隔离(i) **销账**，同批**转正并修复 E54**（神兽读不到自身轨迹）。

> **定性**：本 Phase 承接两条机制 review（「memory 超过 context window 的压缩机制」是否 ready、「多流复用机制」是否完善）与一条新增关注点（pet/beast 任务完成/召回时主 Agent 能否查看返回内容）。
> 一手核实结论：**机制①＝「抢救 + 强制终止」，非「压缩续聊」**（`ctx.messages` 全程不截断，LLM 每轮收全量历史）；**机制②＝「复用同一条 TCP」并发场景不成立 + 记忆隔离单向**（主不读兽、兽可读主）；**pet/beast 返回内容＝死数据**（无工具查询、不落 L2、状态接口不含正文）。
> 上述各项均非规格违约（现有 spec 未明文要求「压缩续聊 / 双向隔离 / 结果可查 / 会话隔离」），故本 Phase 为**缺陷账本（登记）**，实施与否须视产品方向裁决。
> **第四项（E47）＋一条裁决**：承接「开不同 session 对话框时的多流复用」追问 —— 一手核实：复用点＝**共享一个 runtime + 一个 loop 实例**（`ui/api.py:105`；session 只是 `session_id` 标签，非 loop 实例），多流并发在环内**安全**（每轮自建 `ctx`，无 per-call 实例状态），但**检索面不按 session 过滤** ⇒ 会话之间互读记忆（登记 **E47**）。同批裁决：**E45 的 TCP 半条不列为缺陷** —— ADR-0064 的**有意取舍**（线程本地免锁）＋规格未要求「跨线程同一条 TCP」⇒ **不改**，登记为已知局限。
> **E46 已闭（change 0113 / ADR-0106）**：结果可见性改走**查询面接线** —— beast `BeastSession.result_summary()` + `summon` CLI 呈现；pet `PetControl.result` 独立查询面（`status` 面逐字不变）。**两半原写修法皆判据订正**：beast「落 L2」自败（`runtime.py:566` 排除 `beast.*` + beast spec `:89` 封存 ⇒ 主 Agent 检索不到）、pet「`status` 暴露正文」违 `pet-mode` spec `:249`/`:255`。详见 §1.3 订正表与 §4。
> **E47 已闭（change 0114 / ADR-0107）**：用户裁决「隔离边界＝**严格隔离 + 保留全局层**」⇒ 规格先行（8 spec / 9 需求块）→ 测试先行（红 18）→ 实现 → 四门禁（ruff / ruff format / pyright 0-0-0 / **1415 passed**）→ 手工归档 → `openspec validate --all` **30 passed / 0 failed**。**判据订正**：原记「读侧不过滤」一项，实为**读侧 1 + 写侧归属 4 + 绕过通道 1 + id 覆盖 2**（详见 §1.4 订正表）。**附属已闭**：`SessionRegistry.create` 丢更新随 `0115` 顺带闭合（`create` 加进程内 `RLock`，`ui/sessions.py:35`）；仅**同进程线程间**受保护，跨进程并发仍不被声称受保护（ADR-0108 局限①）。
> **E49 新登记并已闭（change 0115 / ADR-0108）**：承接本条需求后半（「右边是会话列表管理…可以选不同的会话**查看记录**或者**继续聊天**」）—— 一手核实：`perceive`（`loop/default.py:432`）是 `ctx.messages` 的**唯一**构造点、每轮只装**一条** user 消息，`planner._build_request`（`planner.py:120-129`）**零截断** ⇒ 服务端**不保留对话历史**，页面刷新即失忆、无法「继续聊天」（登记 **E49**：会话历史不落盘 / 不回灌；同时缺「查看记录」读取面）。修法＝**另立转录存储**（非记忆层级）+ 历史经**新字段** `LoopContext.history` 回灌 + `GET /session/{id}/messages` 读取面 + `GET /sessions` 派生 `title`/`updated_at`。**同批顺带订正一条旧账**：canonical `memory/spec.md:9` 把 L4 写作「原始会话」，与同文档 `:119`/`:181` 及实现（遗忘/压实归档层、检索降权 `relevance.py:24`）相悖 —— 见 §1.5 订正表与 §5.2。
> **E49-B2 已闭（change 0116 / ADR-0109）**：承接本条需求后半的**消费面** —— CLI `session show <id>`（打印转录）+ 顶层 `--session <id>` REPL **续聊** + Web 右栏**会话列表面**（点选查看转录 / 继续对话 / **显式**新建）；**零后端改动**（消费 `0115` 已交付的 `GET /sessions` 与 `GET /session/{id}/messages` 及派生 `title`/`updated_at`）。

## 0. 结论总览

| 编号 | 缺陷 | 判死证据（行号） | 定性 | 修复方向 |
|---|---|---|---|---|
| E44 | 上下文压缩机制未 ready | `loop/default.py:365` `_should_compact` + `:377-399` `_compact`（persist/compact/forget 三步）全程**不截断 `ctx.messages`**；`loop/planner.py:120-128` `_build_request` 无窗口截断 | 「抢救 + 强制终止」非「压缩续聊」 | 若要求真压缩续聊：`_build_request` 前以摘要替换旧历史 |
| E45 | 多流复用「同一条 TCP」并发不成立 + 记忆隔离单向 | `llm_provider/http_pool.py:9-11/70-74` 连接池 `threading.local` 线程本地 + `stdlib_provider.py:147/172/186` 全走 `to_thread` 任意工作线程 ⇒ 并发不共享同一条连接；`runtime.py:566` 主 loop 排除 `beast.*` 而 `_beast_loop` 不排除主 loop 记忆 ⇒ 单向 | 复用仅单线程串行成立；隔离＝「主不读兽、兽可读主」 | TCP：**已裁决不改**（ADR-0064 有意取舍，登记已知局限）；隔离：双向排除或登记共享记忆设计 |
| E46 | pet/beast 任务完成/召回后返回内容死数据 | `beast/manager.py:74-76` result 存 `session.last_result` 但**零读取方**；`pet/core/session.py:146-147` `wake()` 存 `_last_trace_id` 后于 `:153` `return result`，而驱动侧 `driver.py:67` 丢弃返回值；`tools/` 无 beast/pet 工具、不落 L2、CLI 仅 print 状态（`_print_pet_status :1601`） | 主 Agent 无法查看返回内容（beast 真死 / pet 半死） | ✅ **已闭（change 0113 / ADR-0106）**：**两半修法皆订正**，改走**查询面接线**（见 §4） |
| E47 | **会话之间**记忆检索不隔离（附属：会话注册表丢更新） | `context/assembler.py:66-70` → `memory/store.py:95` `read(query, budget)` **只按 source 前缀过滤、无 session 过滤**（而 `loop/default.py:469-474` `remember()` 落库**是带 `session_id` 的**）；`ui/api.py:174-175` 的会话隔离是**调用方手写后置过滤**（只覆盖展示，未覆盖喂给 LLM 的检索）；`ui/sessions.py:33-40` `create` 读回→合并→写回**无锁** | 会话**不是**隔离边界：A 对话框沉淀的事实可进 B 的 system prompt（`planner._system_prompt` → `assembler.build`） | ✅ **已闭（change 0114 / ADR-0107）**：**复用既有过滤管线**给 `read()` 补 session 维度（**不新造机制**）+ **四处写侧归属闭合**（见 §5）。**附属（`SessionRegistry` 丢更新）已闭**（随 `0115`） |
| E49 | **会话历史不落盘 / 不回灌**（刷新即失忆、无「查看记录」读取面） | `loop/default.py:432-443` `perceive` 是 `ctx.messages` 的**唯一**构造点、每轮只装 `[{"role":"user","content":user_input}]` **一条**；`planner.py:120-129` `_build_request` = 一条 system + 全部 `ctx.messages`、**零截断** ⇒ 服务端不保留 per-session 历史，多轮连贯全靠前端回传 + L2 检索；`ui/api.py` 只有 `list_sessions`（`{session_id, mode, created_at}`，无标题无最近活跃），**无取历史端点** | 会话**不可用**：刷新页面即失忆、无法「继续聊天」；32 位 hex 肉眼不可辨，**无法「查看记录」** | ✅ **已闭（change 0115 / ADR-0108）**：**另立转录存储**（`TranscriptStore`，单文件逐行 `O_APPEND`）+ 历史经**新字段** `LoopContext.history` 回灌（不前置进 `ctx.messages`）+ `GET /session/{id}/messages` + `GET /sessions` 派生 `title`/`updated_at`（见 §5.2）。**B2 已闭（`0116`/ADR-0109）**：消费面接线 —— CLI `session show <id>` + 顶层 `--session` 续聊 + Web 右栏会话列表/切换/历史 |

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
| 记忆隔离（主） | `runtime.py:566` | 主 loop 装配 `exclude_source_prefixes=("beast.",)` ⇒ 主 agent 检索排除 `beast.*`（全仓**仅此一处**启用排除，其余为 `memory/protocol.py:54`、`context/assembler.py:28`、`memory/store.py:95` 的管道参数） |
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

**实施期判据订正（change 0113 / ADR-0106，一手复核）** —— 上述证据全部成立，但**修法两半都撞车**，故 §4 的方向被改判；同时补一条证据：

| 原写修法 | 撞车对象 | 订正后口径 |
|---|---|---|
| beast「`recall()` 前 `session.remember()` **落 L2**」 | `runtime.py:566` 主 loop `exclude_source_prefixes=("beast.",)` + `beast-mode/spec.md:89`「记忆分区封存」⇒ 落进去主 Agent **永远检索不到**（**自败**） | 走**查询面**（不落 L2、不改记忆语义） |
| pet「`status`/`snapshot` **暴露正文**」 | `pet-mode/spec.md:249`/`:255` 明文 `status` **SHALL NOT** 外泄主人偏好与任务正文（**违已有 Requirement**，非实现缺口） | 另设**独立查询面**，`status` 面逐字不变 |

**补充证据（新）**：两半**同型** —— **结果对象已经到手，被上层消费点丢弃**（beast：`manager.py:71` 已拿到 `LoopResult` → `:74` 存 `last_result`，`entry.py:1750` `_summon` 只打印状态；pet：`wake()` 已 `return result`，`driver.py:67` 丢弃）。故最小诚实修法是**读取面接线**，而非新造数据流。另注：`BeastSession.remember()` 全仓**零生产调用方**（写入侧实为 `_beast_loop` 的 `DefaultLoop(source=beast.agent_id)`）—— 与本次结果面无关，留作观察（未登记为独立缺陷）。

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

**实施期判据订正（change 0114 / ADR-0107，一手复核）** —— 上述证据全部成立，但缺口**比记载更宽**：原记「读侧不过滤」**一项**，实为**读侧 1 + 写侧归属 4 + 绕过通道 1 + id 覆盖 2**：

| 面 | 原记 | 订正后（一手） |
|---|---|---|
| 读侧（主体） | `read()` 无 session 过滤 | 成立（`memory/store.py:90-111`），唯一过滤是 source 前缀；且 `ui/api.py:174-175` 后置过滤**只盖展示面** |
| 写侧归属 | **未记** | **四处「有键不用键」**：① `context/compactor.py:87/100` 压实产物无 `session_id`；② `skills/router.py:132-146` `_record_miss` 把**每轮任务原话**写全局（普通聊天每轮经 `planner._skill_hints` 触达）；③ `pet/core/session.py:149/:254` `self._loop.run(goal)` 缺会话 ⇒ 宠物轨迹与主线未归属条目**同形不可区分**；④ `orchestration/scheduler.py:375` `profile.loop.arun(goal)` 无会话 + `ui/api.py:160` **有 `session_id` 却不传** |
| 绕过通道 | **未记** | `ctx.notes`（`loop/default.py:312` → `notes/store.py:139` `digest(query)`）**不经 `MemoryStore.read`** ⇒ 会话隔离对其**零覆盖**（本 change 显式裁定为**全局层**，用户裁决） |
| id 覆盖 | **未记** | `compaction.fact.{i}` / `skills.miss.{len(self.misses)}` **不唯一**：每次压实从 0 重数 ⇒ 后一次**静默覆盖**前一次（**残留面登记 E48**） |

**裁决（用户，开工前）**：隔离边界＝「**严格隔离 + 保留全局层**」；历史＝「落盘 + 回灌 prompt」（Change B）；交付＝「拆两个 change」；写侧＝「核心链路 + 同批全修」；`notes`＝「显式定为全局层」。**不可推翻**：phase-19 E2 / change `0048` 已否决每会话独立 `(loop, memory)` 实例 ⇒ 只做「标识透传 + 单店按会话归组」。

### 1.5 E49 会话历史不落盘 / 不回灌（Change B：B1 后端 ＋ B2 前端/CLI）

| 证据点 | 位置 | 实况 |
|---|---|---|
| 消息构造（唯一） | `loop/default.py:432-443` `perceive` | 每轮**新建** `ctx.messages = [{"role":"user","content":user_input}]` **一条**；服务端**不保留**上轮 —— 注释自陈「只观察，不检索记忆」 |
| 请求组装 | `loop/planner.py:120-129` `_build_request` | `[system] + _to_messages(ctx.messages)`，**无窗口截断 / 无摘要替换** ⇒ 上一轮内容**不进**下一轮请求 |
| 多轮连贯的真源 | 前端 `Chat.svelte`（`lines` 为纯内存 `$state`）+ L2 检索 | 刷新即丢；服务端侧无转录 |
| 会话枚举 | `ui/api.py:139` `list_sessions`（旧形） | 条目仅 `{session_id, mode, created_at}`（`ui/sessions.py:37`）——**无标题、无最近活跃**；32 位 hex 肉眼不可辨 |
| 取历史面 | `ui/api.py` | **无** `GET /session/{id}/messages`（`session_messages` 于本 change 新增，`:162`） |

**结论**：用户要的「右边会话列表管理 + 查看记录 + 继续聊天」缺三块 —— ① **转录**（服务端不落盘）；② **读取面**（无端点）；③ **可辨识的列表**（无标题/最近活跃）。**非规格违约**（旧 spec 未明文要求「会话历史落盘 / 回灌 / 转录读取面」），故须**规格先行**（4 spec：`memory` MODIFIED + ADDED、`loop` MODIFIED、`configuration` MODIFIED、`ui` ADDED + MODIFIED）。

**实施期判据订正（change 0115 / ADR-0108，一手复核）** —— 上述证据全部成立，补两条订正：

| 面 | 原记 / 隐患 | 订正后（一手） |
|---|---|---|
| **L4 措辞背离（旧账）** | canonical `memory/spec.md:9`「L2→L3→L4（**原始会话**）」（Change B 计划中记为待校正旧账） | 与同文档 `:119`/`:181`（L4 为**遗忘/压实的归档层**）及实现（`memory/store.py` 遗忘迁 L4、压实后原条目迁 L4；`context/relevance.py:24` `"L4": 0.2` 检索**降权**）**相悖** ⇒ 本 change 一并订正为「L4（归档层：遗忘与压实的下沉目标，检索降权、不参与固化）」。**这是新概念（转录非记忆层级）入 `memory` 包的前提** |
| 「回灌进 `ctx.messages`」 | 直觉修法（把历史前置进 `messages`） | **不可行**：`ctx.messages[0]` 被**四处**当「本轮任务」（`default._task_text:87`、`default._echo:540`、`planner._task:183`），`ctx.messages[1:]` 被 `_action_steps:95` 当动作序列 ⇒ 历史必须走**新字段** `LoopContext.history`（§5.2） |

**附注（录入 ADR-0108 已知局限）**：历史与 reason 阶段 L2 检索存在**重复面** —— `remember()` 条目 `source="loop"` 且同 `session_id`，装配器**只排除 `beast.`** ⇒ 同会话过往轮次**今天就已**作为「相关事实」进 system prompt；本 change 只是加了**时序完整**的第二份。**不修**（修法备查：reason 阶段排除 `("beast.","loop")`，`store.py:111` 支持多前缀且先于排名/预算）。

## 2. E44 修复方向

- 若产品方向要求「压缩续聊」：在 `_build_request` 前对 `ctx.messages` 做摘要替换（保留 system + 压缩中间历史 + 尾部近窗），或在 `_compact` 里把旧历史替换为 compactor 产出的摘要 Message。
- 若维持「抢救 + 强制终止」现状：在契约 / spec 登记为**有意行为**（类同 phase-19 E6 的「压实启发式有意行为」订正），本缺陷销账。

## 3. E45 修复方向

- **TCP**：**已裁决（本次）：不改**。理由 —— ① ADR-0064 的**有意取舍**（线程本地 ⇒ 免锁、无归还竞争）；② 规格「连接复用」场景只要求「复用底层 connection / keep-alive + 失效自动重建」，**未**要求跨线程同一条 TCP；③ 改为「按 origin 单例池」要引入跨线程共享 `http.client` 与归还竞争，收益仅省几次握手。⇒ 登记为**已知局限（每工作线程一条连接）**，不列为缺陷。
- **隔离**：若要求「相互隔离」，给 `_beast_loop` 也注入 `exclude_source_prefixes=("loop",)`（排除主 loop 记忆）；若维持「共享记忆」设计，登记为设计现状。

## 4. E46 修复方向 —— ✅ 已闭（change 0113 / ADR-0106）

**取向（用户裁决，开工前）**：**A 查询面接线** + **① 独立查询面** —— 不落 L2、不改记忆语义、不碰 `status` 隐私面。

- **beast**：`BeastSession.result_summary()`（只读取用**既有** `last_result` ⇒ `{agent_id, has_result, reply, failed}`）＋ `summon` CLI 呈现结果正文与成败（无结果**不打印**结果行）。**否决**「落 L2」——`runtime.py:566` 主 loop 排除 `beast.*` ＋ beast spec `:89` 封存 ⇒ 落进去检索不到（自败）；「允许神兽产物回流主记忆」是**另一件事**，需单独规格变更 + 裁决。
- **pet**：`PetSession.wake()` **在会话内**自留一份 `last_result`（**不进 `snapshot`**、不落盘 ⇒ 只本进程/只最近一次）＋ `PetControl.result()` **独立查询动词**（复用既有 `_resolve` 寻址；CLI `pet result` / `/pet result` 与 CLI **同一实现**）。**否决**「`status` 暴露正文」——`pet-mode/spec.md:249`/`:255` 明文 SHALL NOT 外泄主人偏好与任务正文（**违已有 Requirement**）。**不新造 wake 语义**（`PetControl.wake` 是「恢复让行」的另一动词）。
- **规格**：`beast-mode/spec.md` **ADDED**「Task Result Visibility」（3 场景）；`pet-mode/spec.md` **ADDED**「Task Result Query」（4 场景）。**非** `skip_specs`。
- **落地**：`beast/session.py` `result_summary` / `pet/core/session.py` `last_result` / `pet/core/control.py` `result` / `entry.py`（`_summon` 呈现 + `_print_beast_result` / `_print_pet_result` + pet verb 面）/ `ui/api.py` `pet_command`。测试 `tests/test_beast_result_visibility.py` + `tests/test_pet_result_query.py`（含两条**守护**：`status` 六键逐字不变、结果查询**零 L2 写入**）。**1392 passed**。
- **已知局限**（写进 ADR-0106）：结果不落盘（进程重启即失，与 `status` 同界）；`pet result` 是新暴露面（但未放宽 `status`/`snapshot` 任一层，观测面不接入）；beast 侧无 UIAPI 面（仅 CLI + 会话方法）；`PetWakeDriver` 仍不消费返回值（留存责任放在会话内，驱动零改动）。

## 5. E47 修复方向 —— ✅ 主体已闭（change 0114 / ADR-0107）

**取向（用户裁决，开工前）**：隔离边界＝「**严格隔离 + 保留全局层**」；交付拆两个 change（A＝隔离，B＝会话列表 UI + 历史）；写侧「核心链路 + 同批全修」；`notes` 显式定为全局层。

- **检索隔离（主体，已落地）**：**复用既有过滤管线** —— `MemoryStore.read()` 的 `session_id` 分支加在既有 `exclude_source_prefixes` **同一处**（**先于排名 / 预算 / `reuse_count += 1`**，与既有过滤同口径、可叠加），**未新造第二套记忆检索**。语义：标识**非空** ⇒ 只返回「本会话条目 + 全局层（`session_id == ""`）」；标识**为空串**（未归属调用者）⇒ **不过滤**（fail-open，与既往逐字一致，保住非 UI 调用方与全部既有测试）。
- **写侧归属闭合（同批四修）**：① `Compactor.persist(*, session_id)` —— 保证 `session_id` + id 带会话键（`session_id or "default"`，沿用 store 内既有 `compaction.summary.{key}` 口径，**不另造第二套键**）；② `SkillRouter.match/_record_miss` 未命中条目按会话归属；③ `PetSession` 两处 `run(..., session_id=self.session_id)`（**`observe` 的主人偏好保持全局** —— 刻意知识）；④ `TaskScheduler.run/astream` + `_fan_out`/`_run_subtask`（仅关键字，避 `PLR0917`）+ `ui/api.py:160` 透传。
- **绕过通道**：`notes` **零改动**（显式全局层），只加声明 + 守门用例（`NoteStore.digest/consult/observe_turn` 参数内省）。
- **规格**：8 spec / 9 需求块（`memory` **ADDED**「按会话隔离的检索」5 场景；`context` **MODIFIED** ×2；`loop`/`skills`/`pet-mode`/`orchestration`/`ui`/`notes` **MODIFIED** 各 1）。**非** `skip_specs`。
- **落地**：`memory/store.py` / `context/assembler.py` / `context/compactor.py` / `loop/{protocol,default,planner}.py` / `skills/router.py` / `runtime.py` / `pet/core/session.py` / `orchestration/scheduler.py` / `ui/api.py`。测试 `tests/test_session_isolation.py`（23 例，含**过滤先于预算**的真红测试与**端到端反向守门**「A 会话事实不进 B 的 system prompt」）。**1415 passed**。
- **已知局限**（写进 ADR-0107）：① 存量 `memory.jsonl` 未归属历史条目**全部成为全局层**（跨会话可见，不回填）；② `notes` 不隔离（显式裁定）；③ 专属分区在**未归属读**路径上 fail-open；④ 同会话连续压实 / 跨进程重启的 **id 仍复用覆盖**（既有缺陷 → **E48**）。
- **附属（✅ 已闭，change `0115`）**：`SessionRegistry.create` 的读回→合并→写回**已加进程内 `RLock`**（`ui/sessions.py:35`，随 `0115` 顺带闭合）。**注意边界**（ADR-0108 局限①）：该锁只保证**同进程线程间**不丢更新，**跨进程**同刻并发创建仍**不被声称受保护**。
- **⚠️ 仍开（真·遗留，仅登记未修）**：`write_state` 的临时文件名固定为 `<name>.tmp`，**同一 path 并发写**会交叉写同一 tmp（不同 path 各自独立；当前调用点互不重叠，故**未修**）。它的修法（带 pid/uuid 的唯一 tmp 名）不需要任何裁决，属**待收口项**，见 §7 遗留清单。

## 5.1 新登记 E48：会话维度产物 id 不唯一（残留面）

- **缺陷**：id 只在**单次调用内**唯一，跨调用不唯一 —— `compaction.fact.{key}.{i}` 的 `i` **每次压实从 0 重数** ⇒ 同会话连续压实**静默覆盖**；`skills.miss.{key}.{len(self.misses)}` 的计数器**进程内** ⇒ 进程重启后从 0 重数 ⇒ 同样覆盖。change `0114` 只补了**会话键**（消**跨会话**覆盖），**未**消**同会话内**覆盖。
- **定性**：**非规格违约**（规格只要求「按会话归属」与「id 携带会话键」），属既有写入面缺陷；`store.write` 是同 id 覆盖语义（upsert），故不写坏文件、只丢旧事实。
- **修法方向**：id 改用**内容/时间派生**的唯一键（如 `trace_id` 或单调序号随库落盘），或 `write` 面对同 id 改为「追加不同 id」；须先裁决「同主题压实产物是否应保留历史」。
- **复用点**：Change B（会话列表 UI + 历史回灌）若把历史落盘，会**显著放大**该面（同一会话多轮压实），故列为 Change B 的前置观察项。
- **✅ 处置（Phase 30，change `0117` / ADR-0110）—— 已闭**：拆两子面分别处置 —— **E48-b**（`skills.miss` 计数器：id 改 `blake2b` **内容派生** ⇒ 跨进程不互相覆盖、同任务同会话幂等；`misses` 改 `_MISS_WINDOW = 64` **有界诊断窗口**）**已修**；**E48-a**（`compaction.fact.{key}.{i}` 每次压实从 0 重数）**销账** —— 判为**刷新式派生**（facts 由**当前**记忆重派生，新批次取代旧批次为有意行为；反向若保留历史须同时引入有界淘汰，否则 L2 随压实次数线性膨胀）。见 `phase-30.md` §7 账本。

## 5.2 E49 修复方向 —— ✅ 已闭（B1：change 0115 / ADR-0108；B2：change 0116 / ADR-0109）

**取向（用户裁决，开工前）**：切片＝「**拆 B1 后端 / B2 前端+CLI**」；回灌边界＝「**新增配置键** `loop.history_turns`」；转录落盘＝「**单文件** `messages.jsonl`」；会话标题＝「**自动取首条用户消息**」。`0115` 交付 **B1 后端**，`0116` 交付 **B2 前端 + CLI**（两 change 两 commit）。

- **另立转录存储（非记忆层级）**：新 `src/core/memory/transcript.py` `TranscriptStore` —— 单文件逐行 `O_APPEND`（`os.open(..., O_APPEND|O_CREAT|O_WRONLY)` + **单次 `os.write` 整行**；`Path.open("a")` 带缓冲**跨进程不原子**），`read(session_id)` / `tail(session_id, turns, *, max_tokens)` / `summaries()`；坏行/缺文件降级跳过。**放 `memory` 包**（`loop/default.py` 已 import memory，零新增架构边；放 `ui` 需新增 `runtime→ui` 边）。**明写 SHALL NOT 参与**温度分层 / 排名 / `reuse_count` / 压实 / 固化 / 遗忘 —— 只能经按会话的转录读取面取出。
- **历史走新字段回灌**：`LoopContext.history`（**独立字段**，SHALL NOT 前置进 `messages`）；`perceive` 先 `tail` 再落本轮 user 行（次序不可颠倒，否则本轮回灌两遍）；`planner._build_request` 按「系统提示 → 历史 → 本轮消息」组装；历史 token **计入** `token_used`（否则预算终止与压实触发看不见它）。**双重上界**：`min(最近 N 轮, token 切片)`，切片 = `token_budget // 2`（否则历史自身可能 ≥ `token_budget`，第 1 轮即跑完）。
- **落盘点门控**：`astream` 收尾的转录 append 插在 `remember(...)` **之前**（记忆失败不牵连会话历史）且门控 `not limit_reason`（`:310-311` —— 上面刚把 `ctx.reply` 覆盖为**合成**终止文案，落盘即**谎报模型原话**）。
- **读侧**：`ui/api.py` `list_sessions` 注入转录时**逐条**附派生 `title`（**无用户消息 ⇒ 空串，不伪造**）与 `updated_at`（**无转录 ⇒ 回落注册表 `created_at`**）；`transcript is None` ⇒ 条目形状**逐字不变**（只增不减）。新增 `session_messages(session_id)`（先 `_require_session`，未登记仍 `UI_SESSION_NOT_FOUND`）+ 端点 `GET /session/{id}/messages`。
- **配置**：`loop.history_turns`（缺省 `20`，≥0，`0` = 关闭）三面可配（CLI flag / env / yaml）；走**独立访问器** `history_turns()`（**不动** `loop_limits()` 元组 arity —— 20+ 处解包断言钉死）；经 `LimitsConfigurable.set_limits(history_turns=...)` **热推**。
- **规格**：`memory` **MODIFIED**「分层记忆模型」（**L4 措辞校正**）+ **ADDED**「对话转录持久化（非记忆层级）」；`loop` **MODIFIED**（会话维度那条 + 5 新场景）；`configuration` **MODIFIED**（增键 + 校验场景）；`ui` **ADDED**「会话转录的读取面」+ **MODIFIED**（注册表并发声明收窄为**进程内**）。**非** `skip_specs`。
- **落地**：`memory/transcript.py`（新）/ `loop/{protocol,default,planner}.py` / `configuration/manager.py` / `ui/{api,fastapi_serve,sessions}.py` / `runtime.py` / `entry.py`。测试 `tests/test_transcript.py` / `test_history_replay.py` / `test_history_persistence.py` + `test_serve.py` / `test_session_registry.py` / `test_loop_budget_config.py` 增补。**1462 passed**。
- **已知局限**（写进 ADR-0108）：① 注册表进程内锁对**跨进程**并发创建无效；② 转录单文件随会话数线性增长、读单会话需全扫；③ 超出 N 轮 / 超 token 切片的历史不回灌（有界牺牲）；④ **历史与 reason 阶段 L2 检索重复**（同会话过往轮次**今天就已**进 system prompt，本 change 只是加了时序完整的第二份 ⇒ **不修**，修法备查「reason 阶段排除 `("beast.","loop")`」）；⑤ `conversations.json` 丢失/损坏 ⇒ 注册表空态、转录成孤儿数据但端点按既有 fail-closed 拒绝。

**与 E48 的关系**：本 change **不消解** E48（id 唯一性未动 —— 转录用**追加**（非 upsert），天然无覆盖问题；E48 指 `compaction.*` / `skills.miss.*`，与转录不同面）⇒ 当时保持挂账；**后由 Phase 30（change `0117` / ADR-0110）处置：E48-b 已修、E48-a 销账**。

**B2 消费面接线（change 0116 / ADR-0109）—— 零后端改动**：

- **CLI 读取面**：`session show <session_id>` 打印该会话转录（取自内核回灌的**同一** `TranscriptStore`；无转录 ⇒ 明示、退出码 0；未登记 ⇒ 非零退出码）；`session` 用法串同步。
- **CLI 续聊**：无子命令的交互入口接受**顶层** `--session <session_id>`（`dest="session_id"`，与 `run --session` **同 dest 不冲突** —— `argparse` 子解析器默认值只在命名空间属性**缺席**时套用）。
- **会话标识须到达 `build_app`**：`CLIBridge.connect_impl` 签名由 `Callable[[UIAPILayer], None]` 扩为 `Callable[[UIAPILayer, str], None]`（原先 `repl.py:193` **硬编码** `api.create_session("cli")`）；不绕过 `CLIBridge`（否则它沦为死代码）。
- **`build_app(api, session_id="")` 在懒 import 之前解析会话**：非空 ⇒ `api.session_messages(session_id)`（未登记抛 `UiError`，**先于进入 TUI 拒绝**，且**不静默新建**）；缺省 ⇒ `api.create_session("cli")`（逐字不变）。**续聊渲染**：`on_mount` 把既有转录铺进时间线（user 用 `.echo` + `❯`，agent 用 `.hint`）+ 「↻ 续接会话 <id>（N 条历史已载入）」提示（`.ok`），复用 `escape`、**不新增渲染通道**。
- **Web 右栏会话列表面**：`App.svelte` **单点持有** `sessions` / `sessionId`；`Chat.svelte` 由 `$effect` 按 `sessionId` 拉转录渲染（带**竞态守门** `if (sid !== sessionId) return;`）；`SessionList.svelte` 在**呈现层**按 `updated_at` 降序（**不改**后端响应形状）。
- **显式新建取代惰性建会话**：无选中会话时发送**被拒**并提示「请先新建或选择会话」（避免列表留 32 位 hex 空会话）。
- **规格**：`cli-ops` **ADDED**「会话命令族与交互入口续聊」+ `ui` **ADDED**「Web 会话列表与切换」。**判据订正**：原计划记 `cli-ops` 取 **MODIFIED**，实为**全新需求块 ⇒ ADDED**（先例 change `0028`）；**非** `skip_specs`。
- **落地**：`ui/{cli_bridge,repl}.py` / `entry.py`（`session show` + 顶层 `--session`）/ `frontend/src/{App.svelte,lib/api.js,views/Chat.svelte,views/SessionList.svelte}`；测试 `test_entry.py`（+5）/ `test_repl.py`（+3）/ `test_ui.py`（改 1 增 1）。**1470 passed**。
- **已知局限**（写进 ADR-0109）：① 转录读取**无分页**（`GET /session/{id}/messages` 全量返回，长会话体积随轮数线性增长）；② 前端**无 JS 测试基建**（靠 `npm run build` + 离线冒烟覆盖）；③ **未选中会话被拒**（无「默认会话」回落，属有意行为）。

## 6. 去重边界

- 不重复 E27/B2/C7/C8（phase-20 已列）/ observability/rag/skillhub（phase-22）/ 缺口③（phase-23）/ E30·E31·E32（phase-24）/ E33·E34·E35·E36（phase-25）/ E37·E38·E39（phase-26）/ E40·E41·E42·E43（phase-27）。
- E45-TCP 与 change `0060`/`0066`（ADR-0064「连接复用」）的关系已澄清：ADR-0064 落地「线程本地按 origin 复用 keep-alive」是**有意取舍**，规格只要求「复用连接 + 失效重建」、**未**要求「跨线程同一条 TCP」⇒ 该半条**不列为缺陷**（登记已知局限），无需与 ADR-0064 争边界。
- E46 与 phase-26（E37 神兽记忆命名空间断裂）**不重复**：phase-26 修的是「神兽轨迹混入主记忆污染」（写入侧 source + 读取侧排除），E46 指向「任务**返回内容**主 Agent 不可查」（结果可见性）。
- E47 与 E45 **不重复**：E45-隔离指向「主 loop 与神兽之间」（**source 命名空间**），E47 指向「**会话之间**」（`session_id`）——同属「检索面缺过滤」的同型症状，但边界不同。E47 与 phase-26（E37）亦不重复：E37 是**写入侧** source 注入 + 读取侧 source 排除（跨命名空间），E47 是**同一命名空间内**按会话切分。
- E48（**新登记**，会话维度产物 id 不唯一）与 E47 **不重复**：E47 修的是「条目**归属**哪个会话」（可见性），E48 指的是「**同会话内**连续调用 id 重数 ⇒ 覆盖」（**持久化唯一性**）——`0114` 只补会话键，消的是**跨会话**覆盖，**未**消同会话内覆盖。
- **E49（新登记并已闭）与 E47 / E44 不重复**：E47 是「**记忆检索**面缺会话过滤」（喂给 LLM 的**事实**），E49 是「**对话历史**不落盘 / 不回灌」（喂给 LLM 的**时序**）——两条同属「会话不可用」症状，但**面不同**（检索 vs 转录），故 E47 修完 E49 仍立（`perceive` 依旧每轮只装一条 user）。E49 与 E44 **不重复**：E44 指「**对话历史**在**单轮内**无裁剪 / 无压缩续聊」（`ctx.messages` 全程不截断），E49 指「**跨轮**不保留 / 不回灌」——E44 是「历史太长」，E49 是「历史没有」。E49 的转录**另立存储**（非记忆层级），**不复用** E47 的记忆检索管线、**不改**其过滤口径。
- **E49 与 change `0048`（每会话独立实例已否决）不重复**：转录为**单店 + `session_id` 列**（与记忆同店形态一致），**未**为每会话建独立存储实例 —— 与 `0048` 的裁决同向。

## 7. 红线与裁决

- E44/E45/E46 均非规格违约，**不得以缺陷修复名义 `skip_specs` 强推**；若实施，须视产品方向裁决后**规格先行**。
- E45 若改「双向隔离」会破坏现有「共享记忆」设计（兽读主记忆获取上下文），须先裁决。
- E46（**已闭**）：落地走**查询面**，**不落 L2**（落 L2 会被封存条款挡在主 loop 检索之外 —— 自败）；**不得**改 `status`/`snapshot` 的隐私面（改则违 `pet-mode` 已有 Requirement，须先走过规格变更 + 隐私裁决）；**不得**改 `exclude_source_prefixes=("beast.",)`（会破 phase-26 的 E37/E38/E39 隔离语义）。（原文「落 L2 须复用 `source=beast.<agent_id>` 注入面」随本次裁决**作废**。）
- **E47（已闭）**：原判「现状非违约」（规格未把会话定为隔离边界）⇒ 用户裁决后**规格先行**（8 spec），修法上**复用了既有过滤管线**（`read()` 的 session 分支与 `exclude_source_prefixes` 同点同口径），**未新造第二套记忆检索**。**红线仍守**：不给每个会话建独立 `(loop, memory)` 实例（phase-19 E2 / change `0048` 已裁否决）；不破 `exclude_source_prefixes=("beast.",)`（phase-26 的 E37/E38/E39）；`notes` 不接入会话维度（用户裁决＝全局层）。**附属 `SessionRegistry` 丢更新已闭**（随 `0115` 加进程内 `RLock`；跨进程并发仍不受保护，见 ADR-0108 局限①）。
- **E49（已闭）**：原判「现状非违约」（旧 spec 未要求会话历史落盘 / 转录读取面）⇒ 用户裁决后**规格先行**（4 spec），修法上**另立转录存储**（非记忆层级、单文件 `O_APPEND`），**不复用**记忆检索管线。**红线仍守**：不为每个会话建独立存储实例（phase-19 E2 / change `0048`）；不破 `exclude_source_prefixes=("beast.",)` 与 E47 的会话过滤口径（转录**不是**记忆，`MemoryStore.read` 恒不返回它）；`notes` 不接入会话维度；`session_id == ""` 一律**不落盘、不回灌**（逐字不变）；**不为 title 写注册表**（派生读模型，先例 ADR-0098 拒第二真源）。**B1 + B2 全闭**（`0115` 后端 + `0116` 消费面，两 change 两 commit）—— B2 **零后端改动**，只接消费面（CLI `session show` / 顶层 `--session` 续聊 / Web 右栏列表），**未**放宽任何 fail-closed（未登记 id 仍拒绝）。
- **已裁决（本次）**：E45 的 TCP 半条**不列为缺陷**（ADR-0064 有意取舍），登记为已知局限。
- **E48 / E44 / E45-隔离（Phase 30 收口，change `0117` / ADR-0110）**：三条**均非规格违约**，**未以 `skip_specs` 强推** —— E48-b 与 E54 **规格先行**（`skills` / `memory` / `beast-mode` 三份 delta）；E48-a / E44 / E45-隔离(i) 裁「销账」后**只登记不动代码**。**红线仍守**：**不改**主装配器 `exclude_source_prefixes=("beast.",)`（phase-26 E37/E38/E39 隔离语义）；修 E54 走**最小面**（新增排除面的**例外面** `allow_source_prefixes`，放行**仅自身** `agent_id`，他兽仍排除、主侧可见面逐字不变）；**否决**「排除 `loop`」（与 `memory/spec.md`「按会话隔离的检索」保留全局层相悖，且会造成隔离面不一致）。

## 8. 收口

- **E46 已闭**（change `0113` / ADR-0106）：用户裁决「A 查询面接线 + ① 独立查询面」⇒ 规格先行（两 spec **ADDED**）→ 测试先行（红 17/20）→ 实现 → 四门禁（ruff / ruff format / pyright 0-0-0 / **1392 passed**）→ 手工归档 → `openspec validate --all` **30 passed / 0 failed**。**两半原写修法均判据订正**（beast 落 L2 自败 / pet 改 `status` 违规）。
- **E47 主体已闭**（change `0114` / ADR-0107）：用户裁决「严格隔离 + 保留全局层」⇒ 规格先行（8 spec / 9 需求块，`memory` ADDED + 7 处 MODIFIED）→ 测试先行（新 `tests/test_session_isolation.py`，红 **18 failed**）→ 实现（读侧 1 处 + 写侧归属 4 处）→ 四门禁（ruff / ruff format / pyright 0-0-0 / **1415 passed**）→ 手工归档 `archive/2026-10-06-0114-session-scoped-memory/` → `openspec validate --all` **30 passed / 0 failed**。**判据订正**：原记一项，实为「读侧 1 + 写侧归属 4 + 绕过通道 1 + id 覆盖 2」（§1.4）。**新登记 E48**（会话维度产物 id 不唯一，§5.1）。
- **E49 已闭**（change `0115` / ADR-0108，Change B 前半 = B1 后端）：用户裁决「拆 B1/B2、回灌边界＝新配置键 `loop.history_turns`、转录单文件、标题自动取首条用户消息」⇒ 规格先行（4 spec：`memory` MODIFIED+ADDED、`loop` MODIFIED、`configuration` MODIFIED、`ui` ADDED+MODIFIED）→ 测试先行（新 `test_transcript.py` / `test_history_replay.py` / `test_history_persistence.py`）→ 实现（新 `memory/transcript.py` + `LoopContext.history` + 读取面 + `loop.history_turns`）→ 四门禁（ruff / ruff format / pyright 0-0-0 / **1462 passed**）→ 手工归档 `archive/2026-10-06-0115-session-transcript/` → `openspec validate --all` **30 passed / 0 failed**。**判据订正**：① **L4 措辞背离**（canonical `memory/spec.md:9`「原始会话」与 `:119`/`:181` + 实现相悖 ⇒ 订正为归档层）；② 「回灌进 `ctx.messages`」不可行（四处 accessor ⇒ 走新字段）。**E48 未被本 change 消解**（转录用追加、非 upsert，与 id 覆盖不同面）⇒ 保持挂账。
- **E49-B2 已闭**（change `0116` / ADR-0109，Change B 后半 = B2 前端 + CLI）：承接本条需求后半的**消费面** —— 规格先行（`cli-ops` **ADDED** + `ui` **ADDED**，两新需求块）→ 测试先行（`test_repl.py` 红：`build_app()` 只收 1 位置参；`test_entry.py` 红：`invalid choice`）→ 实现（CLI `session show` + 顶层 `--session` + `CLIBridge.connect_impl` 签名扩为 `(api, session_id)` + Web 右栏会话列表/切换/历史）→ 四门禁（ruff / ruff format / pyright 0-0-0 / **1470 passed**）→ `npm run build`（117 modules / 47.60 kB）+ 离线端到端冒烟（两会话转录 / 派生 `title` / `/session/nope/messages` 404 / 新 SPA 已挂载）→ 手工归档 `archive/2026-10-06-0116-session-list-cli-resume/` → `openspec validate --all` **30 passed / 0 failed**。**判据订正**：原计划记 `cli-ops` 取 **MODIFIED**，实为**新需求块 ⇒ ADDED**。**零后端改动**（复用 `0115` 已交付端点）。
- **（历史留痕，收口前状态）** 当时**余两条**等待产品方向裁决（E44「压缩续聊 vs 有意行为」、E45-隔离「双向隔离 vs 共享记忆」），**未闭附属**仅 **E48**（会话维度产物 id 不唯一）—— 这三条**均已由 Phase 30（change `0117` / ADR-0110）处置**（见下条）。E47 附属的 `SessionRegistry` 丢更新**已随 `0115` 顺带闭合**（`create` 加进程内 `RLock`，`ui/sessions.py:35`）。**Change B（B1 + B2）已全闭**，无余项。
- **Phase 28 账本全闭**（change `0117` / ADR-0110，Phase 30 落地）：余项**三条**分别处置 —— **E48** 拆两子面：**E48-b 已修**（`skills.miss` id 改 `blake2b` 内容派生 + `misses` 有界窗口 `_MISS_WINDOW = 64`）、**E48-a 销账**（压实产物重数＝刷新式派生，有意行为）；**E44 销账**（压实 ≠ 压缩为有意行为，分支 B 不开工）；**E45-隔离(i) 销账**（全局层共享＝用户「保留全局层」裁决的有意结果）。同批**转正并修复 E54**（神兽读不到自身 `beast.<agent_id>` 轨迹 ⇒ 记忆读取面新增排除面的**例外面** `allow_source_prefixes` + `DynamicAssembler.with_allow_source_prefixes` 派生装配器）。**主方向排除 `("beast.",)` 逐字不动**（phase-26 E37/E38/E39 隔离红线守）。**新登记观察项**：宠物 loop 共用主装配器且不传 `source=` ⇒ 宠物轨迹进主命名空间（待裁决，见 `phase-30.md` §7）。
- **下一步＝Phase 30**（Change B 全闭；本 Phase 剩余 E44 / E45-隔离 两条待产品方向裁决 + E48 一项挂账 ⇒ **转交 `coding-plan/phase-30.md` 统一收口**，见该文 §2 裁决点）—— **✅ 已收口（2026-10-06，change `0117`／ADR-0110，1477 passed）**，见 `phase-30.md` §6/§7。

## 9. 遗留清单（Phase 28 全闭后仍在册项）

> 本 Phase **账目已全闭**（E44–E49 全部处置）；下列为**处置时如实登记、未修**的项，按「真·遗留 / 已知局限」两类列出，供后续 Phase 取用。

**A. 真·遗留（未修，且修它不需要任何裁决）**

| 项 | 证据 | 现状 | 修法 |
|---|---|---|---|
| `write_state` 临时文件名固定 | 临时名恒 `<name>.tmp` ⇒ **同一 path 并发写**交叉写同一 tmp | 仅登记（当前调用点互不重叠） | 唯一 tmp 名（pid/uuid）+ `os.replace`；§4 附注 |

**B. 已知局限（有意行为 / 已裁决不改，非缺陷）**

| 项 | 出处 | 内容 |
|---|---|---|
| 转录读取**无分页** | ADR-0109 局限① | `GET /session/{id}/messages` 全量返回，长会话体积随轮数线性增长 |
| 前端**无 JS 测试基建** | ADR-0109 局限② | 靠 `npm run build` + 离线冒烟覆盖 |
| **未选中会话被拒** | ADR-0109 局限③ | 无「默认会话」回落，属有意行为 |
| 注册表锁**不管跨进程** | ADR-0108 局限① | 进程内 `RLock`；跨进程同刻并发创建不被声称受保护 |
| 转录**单文件线性增长** | ADR-0108 局限② | 读单会话需全扫 |
| 超 N 轮 / 超 token 切片**不回灌** | ADR-0108 局限③ | 有界牺牲 |
| **历史与 reason 阶段 L2 检索重复** | ADR-0108 局限④ | 同会话过往轮次**今天就已**作为「相关事实」进 system prompt；**不修**，修法备查「reason 阶段排除 `("beast.","loop")`」 |
| `conversations.json` 损坏 ⇒ 孤儿转录 | ADR-0108 局限⑤ | 注册表空态启动；端点按既有 fail-closed 拒绝（**不放宽**） |
| **E45-TCP 半条** | ADR-0064 / 本 Phase §7 | 「跨线程同一条 TCP」非规格要求，**已裁决不改** |
