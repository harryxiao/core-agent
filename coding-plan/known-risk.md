# known-risk.md · 已知风险登记簿

> **用途**：把散落在各 Phase 文档、ADR「已知局限」、接口注释里的**已知风险 / 有意取舍 / 已知局限**
> 汇总成**单一、可持续登记**的表面，与「Phase 账本」（如 `phase-34.md`，已闭）**互补**：
> Phase 账本记**一次走查**的缺陷账；本簿记**长期**未闭项与**有意不做**的口径。
>
> **新缺陷立项口径**：本轮起，新发现的缺陷/风险在**本簿**取 `E<n>` 编号（续 Phase 34 的 `E87`，
> 故本簿首立 `E88`）**持续登记**；如需成批走查仍可另开 Phase 账本。**只汇总与转引**，不改各源
> 文档；每条**必须**带 `file:line` 或 ADR / change 号，避免二次失真。
>
> **与 `phase-34.md` 的关系**：`phase-34.md` §1~§2 的真缺陷（`E63`~`E87`）已**全闭**（20 change
> `0126`~`0145`）；本簿 §1 只收「**未闭**账」（含 `E27`/`E55`/`C7` 等 phase-34 §3 复述项），§2 搬
> phase-34 §4 的**有意取舍**，§3 收各 change/ADR 的**已知局限**。**不重复**记已闭项。

---

## §1 未闭账（outstanding）

> 现状：**能力已存在但生产不可达**，或**后端未接**。开工须先读「开工口径」——部分账**绑定**前置。

| 编号 | 领域 | 现状（`file:line`） | 开工口径 / 来源 |
|---|---|---|---|
| **E27** | IM 网关 | `IMGateway` 逻辑齐备但**零生产装配**（`src/core/im/gateway.py` 仅自身模块 + 单测 + 配置 spec 映射 + 接口文档；im 规格「分平台接入」要求真实平台 Provider：Telegram/飞书/企业微信…） | **必须与第一个真实 Provider 一并做** —— 单独落代码半（组合根装配 + `im serve`）= 一个「**可启动但永远收不到消息**」的**假入口**，生产上无人往里发消息、宿主侧无从验证。来源：`phase-19.md:104`（E27 行）、`phase-20.md:40-45`（开工口径段）。**前置**：真实平台凭证 + 联网 |
| **E55** | 主 loop | 主 loop **丢弃多余 `tool_call`**（单工具协议只取**首个**，其余静默丢） | `src/core/loop/planner.py:222-225`。与 `E62`（L3 前置，已销账）**同源不同层** ⇒ **保持待议**（是否支持多工具同轮需再裁决）。来源：`phase-34.md:65` |
| **C7** | UI / 语音 | **TTS 后端未接** —— `barge_in` 为**抽象能力**，语音输出无实现 | `doc/03-interfaces/ui-interface.md:19`（`barge_in` docstring：「语音输出为抽象能力（TTS 后端未接）」）。来源：`phase-34.md:66` |
| **—** | composition / distributed | **整包零生产接线** —— distributed 的 oauth2/mTLS/oidc 仅**字段声明**、多设备拓扑**无代码**；composition 于运行时**无生产消费方** | 来源：`phase-34.md:67`、`coding-plan/README.md` §2（标 ✅ 与事实不符，属**已知**）。**注**：composition 的**真内容哈希**口径已由 change `0143` 接通 CLI（见 §3），但**整包**接线仍未落 |
| **—** | evolution | **留出评测生产 runners 未接** ⇒ 候选**恒 `frozen`** | ADR-0112。来源：`phase-34.md:68` |
| **—** | ci-cd | `publisher` **发布通道 `CHANNEL_UNREACHABLE`**（无真实发布通道） | 来源：`phase-20.md`（C 类）、`phase-34.md:69` |
| **—** | deployment | **真实制品仓库未接** | 来源：`phase-34.md:69` |
| **—** | git | `GitClient` **零生产消费者**（phase-20 C2 偏离） | 来源：`phase-34.md:69`。**注**：高危原语（删远程分支 / 历史改写）已由 change `0138` 补齐，但**消费接线**仍未落 |
| **—** | cli-ops | **若干子命令为 stub** | `src/core/entry.py`（运维命令面）。来源：`phase-34.md:70` |
| **E88** | UI / TUI | **TUI 流式 Markdown 表格按行拆断**（渲染为竖线原文，非表格） | **已修（change `0146` / ADR-0138）**。根因：`src/core/ui/repl.py` `_show_delta` 按行固化（`repl.py:485`：`len(text) >= _TAIL_SPLIT` 或 `endswith("\n")` 即 `_freeze_tail`），把表头行拆成孤立块 ⇒ 表格永拼不齐；围栏已有同类保护（`_in_open_fence`，`repl.py:491`）**唯独没覆盖表格**。修：新增 `_in_open_table`（`repl.py:497`）+ `_TAIL_TABLE_CAP`（`repl.py:34`）+ 表格分支（`repl.py:478-484`）。**已知局限**：① 散文行含 ≥2 个 `|` 会**过度延后**固化（有界）；② **Web 端不渲染 Markdown**（`Chat.svelte` 纯文本）属**另一端、不在本 change 面** |
| **E89** | UI / TUI | **流式回显「阶梯式」+ 表格逐行绘制（不够丝滑）** | **已修（change `0147` / ADR-0139）**。根因：① `src/core/ui/repl.py` `_show_delta` **逐 delta** 走 `_touch_tail` → `Markdown.update()`（Textual **整篇 re-parse + 全量 re-layout** 且被 `Markdown.lock` 串行化）⇒ 尾段 O(n²)、渲染队列积压；② 未闭合表格每拍重绘 + 表格**列宽按内容自适应** ⇒ 逐行抽动。修：**合帧节流**（delta 只入缓冲，`_TAIL_FLUSH_S = 0.04` 懒启动 timer 合并渲染一次）+ **表格整块延后渲染**（未闭合不渲染，闭合/超 `_TAIL_TABLE_CAP` 后一次成型）+ `_add` **时序闸**（挂非尾 widget 前先提交挂起尾段）。**已知局限**：① 未闭合长表格有「无可见进度」窗口（>8000 或流尽才显形）；② 40ms 节拍为**常量非配置项**；③ Web/APP 端**不适用** |

| **E90** | memory / 上下文 | **增量滚动摘要缺失**（**已修（change `0148` / ADR-0140）**）。根因：摘要为「**批式重提炼 + 固定 id 覆盖**」，非「现有摘要 + 新片段 → 合并」——`src/core/memory/store.py:369` `_episodic_groups()` 只收 `kind=="episodic"`（旧摘要为 `semantic`，**不进 prompt**）、摘要 id 写死 `compaction.summary.<key>`（**覆盖式**）、`src/core/memory/summarize.py` 旧 `_PROMPT_HEAD` 无既有摘要槽；被覆盖原摘要所引条目已迁 L4（`store.py:401-402`）⇒ 长会话**早期结论逐轮稀释直至丢失**。修：`_summarize_sessions` 投喂前取该会话既有摘要（新 `store.py::_existing_summary`）作为**首元素**并入材料 `material = [prior, *entries]`；`summarize.py::build_prompt` 把既有摘要（`tags` 含 `summary`）渲染为「现有摘要」槽、专设 `_MAX_SUMMARY_CHARS = 2000`；`_commit_summary` 第二参**仍只传本轮 `entries`** ⇒ 既有摘要**只被吸收、不被迁 L4** | **已修**（change `0148` / ADR-0140）；规格已由 `memory`「记忆压实」MODIFIED（新增 Scenario「滚动合并既有摘要（不丢失）」）承接。**已知局限**：① 覆盖写不支持单轮回滚（效应共用 `trace_id=compaction.<key>`，回滚为该会话全量）；② 既有摘要超 2000 字即截断。来源：`Agent-Memory.md` M3（2026-10-07 审查） |
| **E91** | loop / 工具注入 | **工具说明全量注入，无按需筛选** —— `src/core/loop/planner.py:175-177` `_tool_schemas()` 注入**全部** `active_tools()` 的 schema，**无** Query 意图匹配；工具数增长 ⇒ 常驻 token 线性膨胀 | **对照先例可复用**：context 面已有同类机制（change `0140`/ADR-0133 信息地图「目录层 + `tools.context_read` 按需取详情」）。属**优化**，非违约。来源：`Agent-Memory.md` M5 |
| **E92** | memory / 结构化抽取 | **结构化实体抽取缺失** —— 当前只有 `MemoryEntry.kind ∈ {episodic, semantic}` + `tags`（`src/core/memory/protocol.py`），**无** `user_preferences / project_constraints / completed_tasks / key_facts` 四字段 Schema。最近似物为 `notes`（canonical Markdown 真相层，**主题文档**非实体抽取，且纯词法无向量）。**⚠️ 落地红线**：参考方案 Schema 示例把**密钥明文**写入长期记忆（`Agent-Memory.md:35` `"value": "sk-xxxxxxxxx"`），与本仓库红线「**密钥只引用不读取、绝不进日志/记忆**」**直接冲突** ⇒ 若落地，`key_facts` **必须**改**引用式**（`{"entity":…, "ref":"coeffect:…", "value":"<redacted>"}`） | **须先改规格**；属**新能力**，非缺陷修复。来源：`Agent-Memory.md` M4 |
| **E93** | notes / 长任务 | **无「常驻（pinned）笔记」—— 任务级硬约束锚缺失**（**已修（change `0149` / ADR-0141）**）。根因：`notes` 的 Consult **只在 query 命中时注入正文**；未命中仅进 ≤1200 字**标题清单**（`doc/02-modules/notes.md` §3.4、`doc/openspec/specs/notes/spec.md`）。故长任务（跨月/上千轮）中期的硬约束（如「对外接口必须 HTTPS」「Python ≥3.9」）**不保证每轮在场**；每轮**恒注入**的只有 L0 宪法（`Core.md`，**全局、非任务级**）。修：notes 增**「常驻」语义** —— `NoteEntry.pinned` ＋ canonical 行 `- pinned: true`（未置位不输出 ⇒ 零回归）＋ `NoteStore.pinned()/pinned_digest()/set_pinned()`（幂等）＋ **零参**钩子 `PinnedNotesConsult = Callable[[], str]` → `LoopContext.pinned_notes` → planner **独立块**「常驻笔记」（紧随宪法规则、先于相关事实）＋ 三 loop 同注入（主/子/神兽）＋ CLI `notes pin/unpin` | **已修**（change `0149` / ADR-0141）；规格已由 `notes` **ADDED** Requirement「常驻（pinned）笔记（任务级硬约束锚）」+ 6 Scenario 承接。**已知局限**见 §3 ADR-0141 行。来源：`Agent-Memory-LongTask.md` 三.1（2026-10-07 审查） |
| **E94** | notes / memory | **「会话摘要 → canonical 真相层」提升路径无触发**（**已修（change `0150` / ADR-0142）**）—— `0148` 后摘要**滚动累积**，但回喂既有摘要按 `_MAX_SUMMARY_CHARS = 2000` **取前 2000 字**（取**旧端**），超限即在**长时程**缓慢稀释（ADR-0140 已知局限②）；缓解物**已有**（`notes` 覆盖式真相层**不参与压实** + L0 宪法 + 信息地图 pointers），但**「重要结论/硬约束提升进 notes」只靠技能纪律 `skills.notes.consult_build_update` 自觉，无强制、无触发点** ⇒ 长任务早期硬约束可能**不落 canonical**。修（**显式提升路径**）：`MemoryStore.summary_for(session_id)` **只读**访问器 ＋ 新模块 `core.notes.promote.promote_session_summary(...)`（`note_id` 确定性派生 `session-<slug>`、**幂等覆盖**、复用**唯一**写路径 `NoteStore.update()`、**自动置常驻** `pinned=True`、**不接** `EffectTracker`）＋ CLI `notes promote <session-id> [--as ID] [--title T]` | **已修**（change `0150` / ADR-0142）；规格已由 `notes` **ADDED** Requirement「会话摘要提升（promotion）」+ 6 Scenario ＋ `memory` **MODIFIED**「记忆压实」+ 1 Scenario 承接。**已知局限**见 §3 ADR-0142 行。来源：`Agent-Memory-LongTask.md` 二.1 / 三.1（2026-10-07 审查）；与 `E90`（change `0148` 已修）**同源不同层**（前者修**摘要内**稀释，本条补**摘要→canonical**提升） |
| **E95** | notes / 写入安全 | **跨来源误覆写**（**已修（change `0151` / ADR-0143）**）。根因：`notes` 两条写路径**无条件覆写**目标主题、**不看主题由谁产生** —— ① **逐轮写回 `observe_turn`**（`src/core/notes/store.py:191`）每成功轮把「`## 解决过程` + 步骤」覆盖式写回 `slug_topic(task)`，覆写时**只保留 `tags`/`pinned`**、`content` 与 `title` **全量替换** ⇒ 人工撰写 / promotion 产出的笔记只要 `note_id` 撞任务 slug，正文即被**静默替换**；若该笔记 `pinned`，**标记保留、内容被换** ⇒ 此后每轮「任务级硬约束」注入的就是步骤列表（E93 语义被静默污染）。② **提升 `promote_session_summary`**（`src/core/notes/promote.py:24`）无条件覆写派生 `session-<slug>`、强制 `pinned`、改 `source`，撞同 id 人工笔记**无守护**。修（**来源守护**）：`observe_turn` 覆写前读既有笔记，来源**非** `notes.turn` ⇒ **不改写**该主题、沉淀改道派生主题 `<topic>-<n>`（`n` 为 2 起首个「不存在或来源为 `notes.turn`」者）；`promote` 撞**非** `notes.promote` 来源且未给 `--as` ⇒ 不写盘、返回 `None`、CLI 非零退出（给 `--as` 即显式授权覆写） | **已修**（change `0151` / ADR-0143）；规格已由 `notes` **MODIFIED**「Consult → Build → Update 循环纪律」（来源守护条款 + Scenario）＋ **MODIFIED**「会话摘要提升（promotion）」（撞车拒绝条款 + Scenario）承接。**已知局限**见 §3 ADR-0143 行。来源：2026-10-07 记忆三面职责重划探查（`observe_turn` 覆写非自身来源一处为**真缺陷**） |
| **E96** | loop / token 记账 | **记账口径漏掉「固定前缀」、且 `len//4` 对 CJK 约 4× 低估 ⇒ 预算闸门偏晚（真实风险是撞厂商 `context_length_exceeded` 400，非优雅 `TOKEN_BUDGET_EXCEEDED`）**。现状：`ctx.token_used` 只累加 ①本轮 user 输入 `len(user_input)//4`（`src/core/loop/default.py:466`）②回灌历史 `_history_tokens`（`default.py:120-126`，逐条 `content` 取 `len//4`）③每步 `len(str(result.data))//4`（`default.py:527`；工具失败 `result.data=None` ⇒ 记 `len("None")//4=1`）。**不计**：system prompt 全块（宪法 / 常驻笔记 / 相关事实 / 笔记 digest / 技能 / **工具 schema**，装配见 `src/core/loop/planner.py:152-203`）、助手 action JSON（`default.py:502-518`）、observation JSON、模型回复。`len//4` 见 `src/core/context/budget.py:14-19`（注释自承「约 4 字符 ≈ 1 token」）与 `src/core/memory/transcript.py:27-29`。修（**记账覆盖全量装配**）：`perceive` / `observe` 统一经 `_context_tokens(ctx)`（回灌历史 + 本轮消息，口径同 `context.estimate_tokens`）取代原「本轮输入 + 历史 + 每步 `data`」三处各算各的；`LLMPlanner` 新增 `last_prompt_tokens()` 探针（`max(装配全量估算, usage.prompt_tokens)`），loop 侧以 **duck-typing** 消费并取 `max(估算, 探针)` ⇒ **系统提示与工具 schema 计入**、provider 实报抬升**下界**；`_history_tokens` 随之删除 | **已修**（change `0152` / ADR-0144）。原判「属校正 / 优化，非违约 —— 规格 `doc/openspec/specs/loop/spec.md:179-217` 只 SHALL「累计 token 消耗超过预算即终止」，**未**规定记账口径 ⇒ **须先改规格**（先定义口径，再改实现）」**已践行**（先 delta 后实现）。**已知局限**见 §3 ADR-0144 行。另注（**仍在**，另议）：`_should_compact` 比的是 `ctx.rounds`=**工具步数**（上限 `max_rounds=10`）**非对话轮数** ⇒ `_ROUND_THRESHOLD=10` 的「按轮触发压实」**基本是死的**，实践唯一真触发是 token 阀（`src/core/context/compactor.py:35-37`）。来源：本簿 2026-10-07 探查（token 记账 / 窗口感知） |
| **E97** | loop / 上下文窗口感知 | **真实窗口无动态获取；`llm.provider` 是死标签；响应 `usage` 未消费**。现状：窗口唯一来源＝操作者手输 `llm.context_window`（`src/core/configuration/models.py:43`，默认 0 ⇒ 预算回落 `65536`）；全 `src/` **零** `get_model_info` / `max_input_tokens` / `model_info`；**无**三方 LLM SDK（运行时装包仅 `fastapi/uvicorn/textual`；LLM 走 `StdlibLLMProvider` `urllib` 直连，`src/core/runtime.py:314-320` 硬构、**不经** `llm.provider` 分派，`src/core/llm_provider/registry.py:18` 存在但组合根不用）；响应 `usage`（`TokenUsage`，`src/core/llm_provider/stdlib_provider.py:246-252`）**被解析却零消费**；`LLMRequest.max_tokens`（输出侧上限）**无调用方设置**（`src/core/loop/planner.py:138-148`）。 | **配置驱动是既裁**（规格 `doc/03-interfaces/configuration-interface.md:271-272`：**不**开显式 `loop.token_budget` 键，选「由窗口派生」；ADR-0091）⇒ 属**待议增强**，非缺陷。清洁增强（**须先改规格**）：①用响应 `usage.prompt_tokens` **自校准** `token_used`（provider 已解析 ⇒ **零三方依赖**，最优先）；②内置 known-model 窗口表兜底（本地常量）；③三方库（litellm `model_info`）与「核心零三方运行时依赖」**冲突 ⇒ 不取**。**前置**：E96（记账口径）不先修，再准的窗口数亦无意义。来源：本簿 2026-10-07 探查 |

---

## §2 有意取舍（**不算缺陷**）

> 「**有意不做**」的设计决定，非遗漏；若将来要改须**先改规格**。

| # | 取舍 | 口径 / 来源 |
|---|---|---|
| 1 | **Web 无焦点视图** | 沿用 `TaskPanel`，**有意不对称**（`doc/03-interfaces/ui-interface.md:195` 附近；phase-33 明裁）。来源：`phase-34.md:78` |
| 2 | **distributed 契约层先行** | 先立协议模型（AgentCard 签名 / 绑定表 / 连接管理）再接真实传输。来源：`phase-34.md:79` |
| 3 | **HashEmbedder 为降级基线** | 语义检索走 `LLMEmbedder`，**不引**本地语义模型（见记忆 `rag-offline-embedder-decision`）。来源：`phase-34.md:80` |
| 4 | **E62 维持确定性三判据** | 已销账，**非**缺口。来源：`phase-34.md:81` |
| 5 | **deployment `release` 退化哈希（E84-b）** | CLI `release` 无真实制品内容 ⇒ 旧为 `sha256(version)[:16]`；**规格未对 deployment 侧 bundle 哈希设 SHALL**（哈希口径 SHALL 属 composition）⇒ 非违约。**真口径已由 change `0143` 接通**（私有退化哈希已删，改读制品清单经 `composition.packager` 内容哈希发布）；**仍属取舍的只剩** `ReleaseInfo.hash` **无消费方**（写进去的是真口径，但无一处校验它）。来源：`phase-34.md:82`、ADR-0135 |
| 6 | **L1 索引一阶路由未落（E71）** | 规格「跨层检索」（`doc/openspec/specs/memory/spec.md:26-29`）指索引**热路径**；实现为「全库扫描 + 热度加权」= **常驻降级态**（spec「检索失败降级」`memory/spec.md:49-52` 明文允许）⇒ 属**性能面待优化**，非行为违约。来源：`phase-34.md:83` |

---

## §3 已知局限（按 change / ADR 归类）

| 来源 | 局限（`file:line`） |
|---|---|
| **ADR-0136**（change `0144` 时间旅行回滚生产入口） | ① 规格措辞「沿快照**差异**逆序撤销副作用」与实现「按快照 `state["trace_ids"]` 集回滚」**未完全对齐** —— 系统无「检查点之后的 trace」判据（`doc/01-architecture/adr.md` ADR-0136「已知局限①」）；② `Effect.undo` 是**进程内闭包、不可持久化** ⇒ 一次性 CLI 进程内撤销循环**空转**（快照恢复与失败语义仍生效；撤销协同在同进程入口 `serve`/REPL/同 runtime `task` 生效） |
| **ADR-0137**（change `0145` Think 回显） | ① **真端点字段取证被凭据物化阻断**（密钥只引用不读取、绝不回显）⇒ 双键归一按**公开口径**落地、实测转手工验收（`04-testing/test-cases.md` §61 手工项 1）；② **`Chat.svelte` 无 JS 门禁** ⇒ 手工验收（同上手工项 2/3）；③ 思考原文**不进**转录 / 记忆 / 日志 / 事件持久化（`doc/01-architecture/adr.md` ADR-0137「已知局限」） |
| **change `0143`**（E84-a bundle 内容哈希归一） | `ReleaseInfo.hash` 仍**无消费方**（只保证写进去的是真口径）。来源：`phase-34.md:82`、ADR-0135 |
| **change `0140`**（E77 信息地图装配） | `ContextPack.token_used` **口径不变** ⇒ 信息地图的 token 计入未单独切分。来源：ADR-0133 |
| **change `0139`**（E81/E83 Host 心跳 + Desktop 交付面） | ① `touch`/`reap` 今日仍**无生产驱动**（本账补的是规格 SHALL 的**能力面**）；② **Rust 面无门禁** ⇒ 壳编译未经验证，Tauri 打包与壳行为归**手工验收**（`04-testing/test-cases.md` §55）。来源：ADR-0132 |
| **change `0142`**（E85 core-profile 题词模板） | **未取 CLI scaffold**（落盘语义 + 会触碰 30 动词 CLI 基线 ⇒ YAGNI）。来源：ADR-0134 |
| **change `0145`**（同上 ADR-0137） | Web (Svelte) / APP 面**无自动门禁** ⇒ 手工验收（见上） |
| **ADR-0139**（change `0147` TUI 合帧节流 + 表格延后渲染） | ① **未闭合长表格有「无可见进度」窗口**（自表头到达至闭合、或超 `_TAIL_TABLE_CAP`=8000 之间屏幕上不出现该表；出路是加占位 `Static`，**不**回退 `_touch_tail`）；② **40ms 节拍为常量非配置项**（无 CLI/env 面，YAGNI）；③ **Web / APP 端不适用**（`Chat.svelte` 纯文本）。来源：`doc/01-architecture/adr.md` ADR-0139「已知局限」 |
| **ADR-0140**（change `0148` 记忆压实增量滚动摘要） | ① **覆盖写不支持单轮回滚** —— 压实效应**共用** `trace_id = f"compaction.<key>"`，回滚为**该会话全量**（既有口径，非本次引入）；② **既有摘要超 `_MAX_SUMMARY_CHARS`（2000）即被截断**（有界优先）；③ 摘要质量取决于注入模型（未注入则降级不写，既有行为）。来源：`doc/01-architecture/adr.md` ADR-0140「已知局限」 |
| **ADR-0141**（change `0149` 常驻笔记） | ① **常驻正文每轮进模型上下文** ⇒ ⚠️ **绝不**可把**密钥/凭据**写进常驻笔记（已入 proposal 风险节与 `04-testing/test-cases.md` §65 红线）；② 总量有界于 `_MAX_PINNED_CHARS`(4000) 但**无 per-note 上限** —— 多篇各自很长时仍受总量约束、末篇可能被截断；③ notes 写操作**不接** `EffectTracker`（canonical 文档层既有取舍，ADR-0099；pin/unpin 走同一 `update()` 路径 ⇒ 与既有写入面一致）；④ 常驻层**全局** ⇒ 跨会话共享（与既有「刻意知识不参与隔离」一致，**非**缺陷）。来源：`doc/01-architecture/adr.md` ADR-0141「已知局限」 |
| **ADR-0142**（change `0150` 会话摘要提升） | ① **显式触发** ⇒ **无人在场的长任务仍不自动落 canonical**（与 notes「**刻意知识**、非某一轮对话残留」哲学一致；自动触发**另立账**，本 change 刻意不取）；② **自动置常驻** ⇒ 提升正文**每轮进模型上下文**，⚠️ 操作者须在提升前 **review 摘要**，**绝不**提升含密钥 / 凭据的摘要（承 ADR-0141 红线）；③ 与既有常驻笔记**共享** `_MAX_PINNED_CHARS`(4000) 预算，多篇互相挤占、末篇可能被截断（承 ADR-0141 局限②）；④ 提升写操作**不接** `EffectTracker`（承 ADR-0099；可逆性由 canonical 文件本身 + git 体现）。来源：`doc/01-architecture/adr.md` ADR-0142「已知局限」 |
| **ADR-0143**（change `0151` 笔记写入来源守护） | ① **仍无历史版本 / CAS / 三路合并** —— 来源守护堵住**跨来源**误覆写主因，但**同来源**自覆写仍是无历史的「最新即权威」（承 ADR-0099 局限③；回溯交给 git）；② **最小可回溯（`notes/.history/<id>/<ts>.md`）不做** —— 引入新目录 / 新生命周期面，留待另立账；③ `promote` 的撞车拒绝与「空 slug」**共用 `None` 返回** ⇒ 上层靠文案区分，未拆独立错误码（承「不新增错误码」）。来源：`doc/01-architecture/adr.md` ADR-0143「已知局限」 |
| **ADR-0144**（change `0152` loop token 记账） | ① **估算器仍是 `len // 4` 的粗略模型** —— provider 实报可纠正（有 usage 时），但**流式响应 `LLMChunk` 不携带 usage** ⇒ 流式路径只能靠估算（与 **E97** 同源：窗口来源 / 动态获取另立账）；② **`_should_compact` 的轮数维度仍比 `ctx.rounds`（工具步数，上限 `max_rounds`）而非对话轮数** ⇒ 「按轮触发压实」实践上基本不触发，唯一真触发仍是 token 阀（另议）；③ **不改**共享估算器 `context.budget.estimate_tokens`（波及 context 打包与转录切片口径，另议）；④ **不改** `llm.provider` 死标签与「模型真实窗口动态获取」（E97）。来源：`doc/01-architecture/adr.md` ADR-0144「已知局限」 |

---

## §4 非门禁面（手工验收索引）

> 以下面**无自动门禁**（前端 JS / Rust 壳 / 真端点实测 / 真终端目视），以**手工验收**覆盖。

| 手工项 | 位置 |
|---|---|
| Tauri 打包 + Desktop 壳行为（`CORE_PORT` 单点解析、程序化开窗） | `doc/04-testing/test-cases.md` §55（TC-DEPLOY） |
| Think 真端点字段取证 / Web `<details>` / APP 同构 | `doc/04-testing/test-cases.md` §61（TC-THINK）手工项 1~3 |
| TUI 流式表格目视（表格整块 / 围栏回归） | `doc/04-testing/test-cases.md` §62（TC-TABLE）手工项 1~2 |
| TUI 流式回显丝滑化目视（不再阶梯 / 表格一次成型 / 时序不乱） | `doc/04-testing/test-cases.md` §63（TC-SMOOTH）手工项 1~3 |

---

## §5 关联

- Phase 账本（已闭）：`coding-plan/phase-34.md`（`E63`~`E87` 全闭）、`coding-plan/phase-32.md`（`E56`~`E60`）
- 架构取舍：`doc/01-architecture/adr.md`（各 ADR「已知局限」）
- 测试索引：`doc/04-testing/test-cases.md`
- 未闭账复述源：`phase-34.md` §3、`phase-19.md:104`、`phase-20.md:40-45`
- 外部参考审查：`Agent-Memory.md`（本地 Agent 长对话记忆压缩方案；2026-10-07 审查 ⇒ 取精华弃糟粕，立 `E90`~`E92`）；`Agent-Memory-LongTask.md`（跨月级超长期研发任务记忆方案；2026-10-07 审查 ⇒ 取精华弃糟粕，立 `E93`~`E94`；**不取**其「里程碑永久删除 / 单库无隔离 / 三方依赖」等红线项）
