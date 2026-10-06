# Phase 29：orchestration 子 Agent 动态调度 + 运行态实时回流 + 会话导航

> **状态**：🔨 **部分落地**（能力扩展**提案**，非纯缺陷账本；四处缺口 E50~E53，串行/并发**载体已存在**，缺的是「动态决策」与「可见性/可导航」两层）—— **2026-10-06 已 review**：§0.6 判据订正（4 处）+ §6 拆分建议 + §7 登记（E55 / 调研不可达 / 两条红线），**§4 四裁决点已认可**；**change A（E51 事件回流）已落地**（change `0121` / ADR-0114，2026-10-06）、**change B（E53 HTTP 面 + Web 任务区）已落地**（change `0122` / ADR-0115，2026-10-06）、**change C（E50 策略层）已落地**（change `0123` / ADR-0116，2026-10-06）、**change D（E52 TUI 子任务运行态 + 里程碑详情）已落地**（change `0124` / ADR-0117，2026-10-06）⇒ **四条缺口 E50~E53 全闭**
> **定性**：承接用户对 orchestration 子 Agent 机制的 4 点需求——①主 Agent **依据任务难易度动态决策串行 or 并发**；②串行/并行都需 CLI + web/app **动态显示子 agent 主题 + 运行状态**；③可**进入子 agent 查看运行详情**、完成可**回到主 Agent**。一手核实结论：**串行/并发两条载体均已落地**（串行＝`delegate` 工具阻塞 await + 波次间串行；并发＝`TaskScheduler` 波次内 `asyncio.create_task` fan-out + `Semaphore`），但**四处需求缺口坐实**——波次划分依据是**依赖拓扑**而非难易度（`Subtask` 无 difficulty 字段）、子 agent **中间事件被吞**（`arun` 只回三态）、CLI 仅**只读折叠块**无会话切换、web/app **无任务栏渲染**。

## 0. 一手核实（证据与行号，claude code 定位用）

| 缺口 | 判据 | 代码实况（已逐字核实） |
|---|---|---|
| E50 难易度动态决策缺失 | `Subtask` 无难度字段 + 波次划分只看依赖 | `orchestration/models.py:32-39` `Subtask` 字段仅 `id/goal/acceptance/depends_on/priority`，**无 difficulty**；`orchestration/decomposer.py:85-95` `_build_waves`：`level[sid] = 1 + max(依赖层号)` ⇒ 波次**纯依赖拓扑**，难易度不参与 |
| E51 子 agent 运行状态实时回流缺失 | 中间事件被吞，只回终态 | `orchestration/scheduler.py:399-401` `result = await profile.loop.arun(goal)` **只拿终态 `LoopResult`**；`loop/default.py:211-223` `arun` 内仅捕获 `loop_started/loop_finished/loop_failed` 三态，中间 `reason`/工具事件**丢弃** |
| E52 CLI/Web 进入子 agent + 回主 agent 切换缺失 | 只读折叠块、无会话切换 | `ui/repl.py:604` `Collapsible(detail, title="▸ 子任务 …", collapsed=True)` **只读折叠块**（`_open_subtask`/`_complete_subtask` 仅打开/关闭，无进入会话、无"回主 Agent"）；全仓 grep 无 `switch`/`active_agent` 切换面 |
| E53 web/app 任务栏渲染缺失 | 无 subtask 渲染、无事件转发 | `ui/web_bridge.py` 仅桥接层；`ui/fastapi_serve.py` 无 `subtask_started/completed` 消费、无任务栏/子 agent 面板渲染 |

**串行/并发载体（已存在，本 Phase 不重建）**：
- **串行派发**：`runtime.py:770-781` `_delegate` 阻塞 await `_dispatch(task)` → `runtime.py:767` `await profile.loop.arun(task)` 拿 `LoopResult` 回传（主等子）；`scheduler` 波次之间天然串行。
- **并发扇出**：`scheduler.py:206-208` `asyncio.create_task(self._fan_out(...))`；`scheduler.py:320` `_fan_out` + `:326` `asyncio.Semaphore(self._max_concurrency)` ⇒ 波次内并发（**协程并发**，非线程并行）。

## 0.5 参照设计与调研（2026-10-06，为 E50 决策器提供判据参照）

> 完整报告见 `temp/research/orchestration_parallelism_survey.md`，本段为落地精简版。

### 0.5.1 一手补充核查：主 loop 多任务默认路径（问题①结论）

| 事实 | 证据 |
|---|---|
| 默认入口是**主 loop** | `api.py:185` → `loop.astream(...)` |
| 主 loop **只取第一个 tool_call，其余丢弃** | `planner.py:224-225`（注释明写只取 first）——非"串行执行多个"，更非并行 |
| 子 agent **阻塞串行 await** | `runtime.py:772` `delegate` 工具阻塞 await |
| 并发能力在**独立入口** | `TaskScheduler` 波次并发，`api.py:189 run_task` / `runtime.py:839-841`，非主 loop 默认路径 |

**结论**：两条路径都是活的（**非死代码**），但「LLM 返回多任务」场景默认落在主 loop → 串行 → **丢弃第 2 个及之后的 call**；主 loop 内**无任何动态串/并决策点**（决策点=零，非"有但没生效"）。这与 E50「缺统一串/并决策点」同源——当前是"写死串行 + 多余 call 丢弃"，并发在另一条独立入口，两者**割裂**。

### 0.5.2 主流框架串/并决策范式（三类）

| 框架 | 串/并决策者 | 决策依据 | 运行时动态决策? |
|---|---|---|---|
| CrewAI | 人（配置） | `process` 枚举（新版**仅 `sequential`/`hierarchical`**，Consensual 已移除） | ✗ 固定 |
| AutoGen | 人（选 pattern） | 设计模式（Sequential / Concurrent / GroupChat / Handoffs / MoA / Debate） | ✗ 固定 |
| LangGraph | 图拓扑 + LLM（局部） | 边依赖（同 super-step 无依赖节点并发）+ routing 用 `with_structured_output` 让 LLM 输出 decision | 部分（仅 routing/拆解） |
| Claude Code | LLM（主 agent 自主派发） | **依赖关系**：无依赖 → 并行 spawn subagents；有依赖 → 链式 | ✓ 自主（有**并发上限**） |
| Codex | LLM（主 agent） | 依赖关系（AGENTS.md 定义 subagent，sandbox 并行） | ✓ 自主 |
| **core-agent（现状）** | **无**（写死） | 主 loop 串行丢弃 / 独立 run_task 并发，两入口割裂 | ✗ **无统一决策点** |

**核心洞察**：主流框架串/并决策只有三类——①**显式声明式**（CrewAI/AutoGen，决策在人）；②**图结构式**（LangGraph，拓扑决定并发，LLM 只做局部 routing）；③**LLM 动态驱动**（Claude Code/Codex，主 agent 自主判依赖 + 并发上限保护）。**无任何框架做「按难易度自动串/并」的运行时决策** ⇒ core-agent 的难易度决策是**独有需求**。

### 0.5.3 对 E50 的决策参考：模型自主判依赖 + 并发上限保护

- **Claude Code 是唯一接近「运行时动态决策」的范本**，判据=**依赖关系**（官方文档原文："spawn multiple subagents to work simultaneously … works best when the research paths don't depend on each other"），并设**并发上限（Concurrent subagent limit）**保护。
- **对 E50 的启示**：纯「难易度」判据无法处理「任务间有依赖」的情形（难但无依赖可并发、易但有依赖必串行）。建议决策器判据=**四元组合**：`依赖拓扑（硬约束，已有 _build_waves）→ 难易度（加权项，用户需求）→ 模型自主判依赖（Claude Code 范式）→ 并发上限保护`，而非单一难易度阈值。
- **三条 gap 坐实**（与 phase-29 对应）：①主 loop 丢弃多余 call（见 0.5.1）；②缺统一串/并决策点（=E50）；③缺 CLI/Web tab 式多 agent 导航（=E52/E53）。

## 0.6 判据订正（2026-10-06 review：逐处复核代码后）

> **总判**：四缺口**全部属实、定位准确**；但 **E51 的成本被写大**（外送通道已存在）、**E53 的归因写偏**（缺的是 HTTP 暴露与前端，不是事件转发）、**E52 两处隐性成本未写**、**E50 漏三条硬约束**，且 §0.5 新增的 gap ① **在 §3 无任何落地项**。

| # | 原判 | 订正（复核后） | 证据 |
|---|---|---|---|
| E51 | 「scheduler 改走 astream + 新事件契约」 | **外送通道已经建好**：`Emit` 已是 `_run_subtask` 形参、`_fan_out` 已透传、`run` 已是 async generator（`asyncio.Queue` 排水）、`UIAPILayer.run_task` 已映射为 `task.*` SSE ⇒ 真实改动 = `_run_subtask` 内 `arun` → `astream` + `emit(subtask_progress)`，**外送通道零改动**（**落地订正**：「层面零改动」**不完全** —— 协议声明面 `LoopPlugin.astream` 形态错标（协程 vs 异步生成器）+ **5 处测试替身**须由 `arun` 迁到 `astream`，见 ADR-0114 判据订正 (b)） | `scheduler.py:35/321/346/206-215`；`api.py:189-196` |
| E51 | 中间事件含 `reason_started` | **`reason_started` 不存在**；`astream` 实际产出 `loop_started`/`reply_delta`/`action_started`/`action_completed`/`step_completed`/`loop_finished`/`loop_failed`。**`reply_delta` 必须排除**（模型流式原文：既洪泛又暴露原始输出） | `default.py:216-237/267/385` |
| E53 | 「`fastapi_serve` 无 subtask 消费 ⇒ 缺事件转发」 | **转发层已存在且完好**（`api.py:189-196` 已映射 `task.*`）；真缺口是 **① HTTP 面未暴露**（`fastapi_serve.py:171-182` 的 11 端点**无 `/task` 路由**；`run_task` 的生产消费者**只有 CLI** `repl.py:509-525`）**② 前端为零**（3 视图、`lib/api.js` 无 task 导出） | `api.py:189`；`fastapi_serve.py:171-182`；`frontend/src/**` |
| E52 | 「折叠块升级为子会话视图」 | 判据成立（`_open_subtask`/`_complete_subtask` 只开关），但**两处隐性成本未写**：①「回到主 Agent」实为**焦点状态机 + 输入路由语义**（全仓无 switch/`active_agent` 面，REPL 无当前会话可变态）；②「子 agent 消息流」**数据源不存在** —— 转录只注入主 loop（change `0115` 明文），子 loop 不接转录、`ctx.messages` 不跨回合 | `repl.py:596-620`；`runtime.py:165/664/683` |
| E50 | 「加 difficulty + 策略层」 | 三条硬约束漏记：(a) **`plan_to_dict`/`plan_from_dict` 逐字段枚举** ⇒ 加字段须**同改两处**，否则断点续跑**静默丢字段**；(b) 生产难度是 **LLM 自报**（改 prompt `_DECOMPOSE_SYSTEM` + parse）⇒ **弱信号、不可确定性验证**，测试须打桩 planner；(c) **`max_concurrency` 缺省 4 且 `runtime.py` 完全不传** ⇒ 不接线则「并发上限保护」空转（与 E15 同型） | `models.py:85-125`；`planner.py:19-25/76-99`；`scheduler.py:97/112` |
| **gap ①** | §0.5.1/§0.5.3 列为「坐实的 gap ①」 | **§3 无对应落地项**，E50 落地也不碰主 loop；而修它须改 **L3 协议**（`Action` 为单工具协议，注释明写「并行多调用取首个」）⇒ 爆炸半径**大于本 Phase 其余之和**。**处置：登记为独立缺口 E55，不在本 Phase 落地**（见 §7） | `planner.py:222-225`；`api.py:185` |

**引用证据不可达（E9 型）**：§0.5 引用的 `temp/research/orchestration_parallelism_survey.md` **不在仓库**（`temp/` 整个目录不存在）。该调研已是 E50 的判据来源 ⇒ 结论须固化进本文件或 `doc/`（§0.5.2 的框架对比表当前**只有结论无出处**）。

## 1. 范围与定位

- **分层**：L3.5 `orchestration`（调度策略/事件回流）+ L7 入口 `ui`（repl / fastapi_serve / web_bridge）呈现与导航。
- **不在范围**：不新建子 Agent 执行载体（`DefaultLoop.arun` + `SubAgentProfile` 已存在）；不改 `tools.delegate` 语义（其阻塞 await 是「主 Agent 主动委派」的**有意设计**，与 `TaskScheduler` 波次并发是**两条正交通路**）。

## 2. 需求映射（4 缺口 → 落地件）

| # | 缺口 | 用户需求 | 落地方向 |
|---|---|---|---|
| E50 | 难易度动态决策 | 「依据任务难易度动态决策串行还是并行」 | 决策器判据=**四元组合**（见 §0.5.3）：`依赖拓扑（硬约束）→ 难易度（加权）→ 模型自主判依赖 → 并发上限`。`Subtask` 增 `difficulty` 字段（或难易度由 decomposer 评估写入）；`_build_waves` 之后的**调度策略层**据此决定同波次无依赖子任务「并发扇出 vs 串行逐个」；依赖拓扑仍为硬约束（有依赖必串行） |
| E51 | 运行状态实时回流 | 「动态显示子 agent 主题 + 运行状态」 | `scheduler` 改走 `loop.astream(goal)` 消费中间事件（**订正见 §0.6**：事件名是 `action_started`/`step_completed` 等，**无 `reason_started`**；**排除 `reply_delta`**），`emit(LoopEvent("subtask_progress", {...}))`；**外送通道已存在**（`emit` 已是 `_run_subtask` 形参、`run` 已排水、`run_task` 已映射 `task.*` SSE）⇒ 层面零改动 |
| E52 | 进入子 agent + 回主 agent | 「进入子 agent 查看详情，完成回到主 Agent」 | CLI：折叠块升级为**可进入的子会话视图**（子 agent 消息流 + 运行态）+ 显式「回到主 Agent」入口；Web：右栏任务栏 + 子 agent 面板 + 主/子切换 |
| E53 | web/app 任务栏渲染 | 「CLI 和 web/app 都动态显示」 | **订正见 §0.6**：事件映射层（`api.py:189-196`）**已存在** ⇒ 真缺口 = ① **HTTP 面未暴露**（`fastapi_serve.py` 的 11 端点**无 `/task` 路由**，`run_task` 生产消费者只有 CLI）+ ② **前端为零**。⇒ 新增 `POST /task` SSE 路由 + 前端任务区（**复用右栏位置**），渲染任务列表（子 agent 标题 + 状态徽标），点击进入详情、返回主会话 |

## 3. 落地拆解

> **顺序**：规格先行（E50 改 `orchestration` spec、E51 改事件契约、E52/E53 改 `cli-ops`/`ui` spec）→ 测试先行 → 实现 → 门禁四命令全绿。

### 3.1 E50 难易度动态决策（规格先行）✅ **已落地**（change `0123` / ADR-0116，2026-10-06）

> **落地**：`Subtask.difficulty`（三档 + 归一）+ 同波次调度策略（`off` 缺省沿用拓扑并发 / `difficulty`
> 含 hard 波次串行）+ `orchestration.{difficulty_policy,max_concurrency}` 两键 + 组合根注入。
> **判据订正 4 条**：① 第 4 条「**缺省 = 全串行**」**字面订正**为「**缺省沿用拓扑并发**」（用户裁决：
> 与 spec「并行扇出」及既有并发用例字面冲突 = 能力回归；原意「弱信号不得直连并发开关」**保留**，
> 但由「缺省即串行」改为「缺省不变、仅 `difficulty` 收窄」）；② 第 1 条「决策器**四元**组合」本期只落
> **三判据**（依赖拓扑 + 难易度 + 并发上限），「模型自主判依赖」延后（§4 裁决②）；③ 归一含**去空白 +
> 小写**（`"HARD"` ⇒ `hard`，非降级 `medium`）；④ 第 3 条「`_fan_out` **之前**新增调度策略」实为
> **只改 `Semaphore` 上限**（`_wave_limit`），波次划分 `_build_waves` **逐字不动**（依赖拓扑仍是硬约束）。
> 已知局限 6 条（见 ADR-0116）。门禁：ruff / format / pyright 0-0-0 / **1589 passed** / validate 30-0。
1. `orchestration/spec.md`：`Subtask` 增 `difficulty`（如 `"easy"|"medium"|"hard"` 或数值档）+ 调度策略条款（决策器四元组合，见 §0.5.3：`依赖拓扑硬约束 → 难易度加权 → 模型自主判依赖 → 并发上限保护`）；**注意是 ADDED 非 MODIFIED**（新增能力，先例 change `0028`）。
2. `decomposer.py`：难易度由**生产拆解器（`LLMSubtaskPlanner`）自报** ⇒ 实为改提示词 `_DECOMPOSE_SYSTEM`（`planner.py:19-25`）+ `_parse`（`:76-99`）；**须同改 `plan_to_dict`/`plan_from_dict`（`models.py:85-125`）**，否则检查点跨进程往返**静默丢字段**；测试须打桩 planner（弱信号，不可确定性验证）。
3. `scheduler.py`：`_fan_out` 之前新增**调度策略**——依赖拓扑仍由 `_build_waves` 保证（硬约束，有依赖必串行）；同波次无依赖子任务按难易度决定串/并（高难度串行避免资源争抢/上下文污染、低难度可并发），并设**并发上限**——**须由组合根把 `max_concurrency` 传入 `TaskScheduler`**（`scheduler.py:97` 缺省 4、`runtime.py` 当前**完全不传**；不接线则该判据空转，与 E15「可注入但唯一调用点不传参」同型）。
4. 阈值/策略须**可配置**（`configuration` 键；全仓 `orchestration` 现**无任何配置键** ⇒ 走 `ConfigSpec` + 独立访问器，先例 change `0115` 的 `history_turns`），**缺省 = 全串行**（见 §4 review 建议）；模型自主判依赖作为后续演进项。

### 3.2 E51 运行状态实时回流（事件契约先行）✅ **已落地**（change `0121` / ADR-0114，2026-10-06）

1. 事件契约增 `subtask_progress`（含 `subtask_id`/`task_id`/**`event`**/**`data`**/`ts`；**落地订正**：键名不取草记的 `event_type`/`payload` —— 后者会造出 `LoopEvent.payload["payload"]` 嵌套同名）；`data` **须白名单化**（`action_started` 可能含工具参数/路径/正文 ⇒ 守「密钥只引用不读取、绝不进日志/记忆/事件面」，见 §7）。
2. `scheduler.py:398-401` 由 `arun` 改为 `async for event in profile.loop.astream(goal)`，把**里程碑**事件（`action_started`/`action_completed`/`step_completed`）转译 emit（**排除 `reply_delta`**），终态仍归一为 `SubtaskOutcome`。**外送通道无需改动**（`emit` 已是 `_run_subtask` 形参 `:346`、`_fan_out` 已透传 `:321`、`run` 已排水 `:206-215`、`run_task` 已映射 `task.*` SSE `api.py:189-196`）。
3. `DefaultLoop.arun` 保持「三态归一」**语义**不变（供 `delegate` 等需要终态的调用方）；所需 `astream` **已存在且已在 `LoopPlugin` 协议上**（`protocol.py:107`，`AgentProfile.loop` 即 `LoopPlugin | None`）⇒ **不重复造**。**落地订正**：归一实现抽为 `core.loop.collect_result`（`arun` 变其薄壳），使编排层与同步入口共用**单一真源**（两处各写一遍必然漂移）。

### 3.3 E52/E53 会话导航 + 任务栏（消费面接线）
1. `repl.py`：**本期收窄为「只读详情 + 实时状态」**（即 E51 的 CLI 呈现面：展开区显示里程碑事件 + 状态徽标）。「进入子 agent 会话 / 回到主 Agent」= **焦点状态机 + 输入路由语义**（全仓无切换面），且子 agent 消息流**无数据源**（转录只注入主 loop，change `0115`）⇒ **登记后续**（见 §0.6 E52、§7）。
   ✅ **已落地**（change `0124` / ADR-0117，2026-10-06）：`_add_task_widget` 增 `subtask_progress` 分支 → `_progress_subtask`（工具类里程碑**复用 `format_action_event`** ⇒ 友好名 + 耗时，**不**暴露内部 `tool_id` / `args` / `output`；轮次级落「第 N 轮完成/失败」；无对应折叠块 ⇒ 静默忽略）+ `_open_subtask` 标题加**运行态徽标** `⟳`（收尾由 `_complete_subtask` 替换为 ✓/✗）。**判据订正 2 条**：① §6 表 D 行「可验证性：**低**（Textual 无测试基建）」**不成立** —— 本仓**已有** headless Textual 基建（`app.run_test()` + `_timeline_text` + 断 `Collapsible.Contents.display`），本 change 四用例全部由它钉死 ⇒ 实为**高**；② 「依赖 A 的呈现面」表述偏松 —— A 交付**数据面**、本 change 是**消费面**，且 B 已在 Web 侧完成等价消费（`milestone(ev)`）⇒ 呈现口径可直接对照 Web。**决策 5 条**（ADR-0117）：消费面接线不建旁路 / 复用动作行口径 / 无块静默早退 / TUI **不**预生成 pending 条目（对话流 vs 清单面板的有意差异）/ **不触** `format_task_event`（非交互 `core-agent task` 输出粒度逐字不变）。前端/非交互 CLI **零改动**。
2. `fastapi_serve.py`：**新增 `POST /task` SSE 路由**（复用 `UIAPILayer.run_task`，其事件**已**映射为 `task.*`）→ Web 任务区（标题 + 状态）+ 子 agent 详情面板 + 主/子切换；前端 `lib/api.js` 增 `runTask` 流式客户端、新增任务区视图（**复用右栏位置，不与会话列表混池** —— 会话持久 vs 任务在途，须定义任务收尾后回落）；前端**无 JS 测试基建** ⇒ 端点层用 pytest 断 SSE 帧序列，前端 build + 手工冒烟。
   ✅ **已落地**（change `0122` / ADR-0115，2026-10-06）：`POST /task`（11→**12 端点**）+ `frontend/src/views/TaskPanel.svelte`（右栏上方独立区块，与会话列表**并列不混池**）+ `lib/api.js` 抽 `postSSE` 共用、增 `runTask`。**落地订正 3 条**：① 详情面板**收窄为事件载荷已有字段**（`§3.3` 草记的「主/子切换」**不做** —— 与 `§4` 裁决③末句、`§0.6` E52、`§7` 红线② 一致：子 agent 消息流**无数据源**）；②「复用右栏」取**上下两独立区块**而非替换会话列表（两个生命周期不争同一槽位）；③ 「收尾回落」在**数据面**即 `task.task_finished`/`task.task_failed` 把任务移出在途列表（**不**谎报为会话注销）。**转发层零改动**（`api.py:189-196` 映射与 change `0121` 的 `subtask_progress` **原样透出**）—— 真缺口就是「HTTP 面未暴露 + 前端为零」，与 `§0.6` E53 判据一致。

### 3.4 门禁
- `ruff check/format` + `pyright` + `pytest -q` 全绿；`validate --all` 全绿（spec 改动须同步 interface 契约）。
- 新增单测覆盖：难易度→串/并策略、中间事件转发、会话切换往返。

## 4. 裁决点（须用户拍板后规格先行）

1. **E50 策略形态**：难易度档位（三档 `easy/medium/hard`）还是数值分（0~1）？阈值硬编码还是进 `configuration`？（建议：三档 + `configuration` 可配，缺省 hard 串行 / easy·medium 并发）
2. **E50 决策器判据**：是否在难易度之外引入「模型自主判依赖 + 并发上限保护」（Claude Code 范式，§0.5.3）作为第二判据？还是仅「依赖拓扑 + 难易度 + 并发上限」三判据（更轻）？（建议：先落地三判据，模型自主判依赖作为后续演进项）
3. **E52/E53 交互范围**：CLI 子会话是「内嵌面板」还是「独立全屏视图」？Web 任务栏是否复用现有右栏会话列表（phase-28 `0116` 已落地）还是新建任务面板？
4. **E51 回流粒度**：中间事件全量回流（重）还是只回「里程碑事件」（reason 开始/工具调用开始/完成，轻）？（建议：轻量里程碑事件 + 终态，避免 web 端洪泛）

> **review 建议（2026-10-06，已认可）**：
> ① E50 取**三档 + `configuration` 可配**，但**缺省 = 全串行**（难度是模型自报弱信号 + `max_concurrency` 未接线 ⇒ 不得把不可靠信号直连并发开关）；
> ② 采纳**三判据先行**（依赖拓扑 + 难易度 + 并发上限），但**必须补「`max_concurrency` 由组合根注入」**（否则上限空转）；模型自主判依赖延后；
> ③ CLI 本期**只做只读详情 + 实时状态**，「进入会话/焦点切换」登记后续；Web **复用右栏位置新建任务区、不与会话列表混池**；
> ④ 只回里程碑，**显式排除 `reply_delta`**。

## 5. 去重边界

- **不重复** phase-28 E46/E47/E49（pet/beast 返回可见性、会话隔离、会话历史落盘回灌——那是**记忆/转录**维度，本 Phase 是**编排运行态**维度）。
- **不重复** phase-27 原生执行器（进化引擎维度）。
- **不重建** 串行/并发载体（`delegate` 阻塞 await + `TaskScheduler` fan-out 已存在，本 Phase 只补「决策策略」与「可见/导航」两层）。
- `tools.delegate` 阻塞 await **不改**（主 Agent 主动委派语义，与波次并发正交）。

## 6. 下一步

1. 用户对 §4 四处裁决点拍板（策略形态 / 决策器判据 / 交互范围 / 回流粒度）—— **review 建议已列于 §4 末**。
2. 裁决后**拆 change 落地**（评审结论：原「一个 change 落地」不可行 —— 四个面彼此独立，且 E50 另触持久化面与配置面）：

   | change | 内容 | 成本 | 可验证性 |
   |---|---|---|---|
   | **A** | ✅ **已落地**（change `0121` / ADR-0114）：**E51 事件回流**（最小，可先行）：`subtask_progress` + payload 白名单 + 排除 `reply_delta` | 小 | 高（pytest 断事件序列） |
   | **B** | ✅ **已落地**（change `0122` / ADR-0115）：**E53 HTTP 面 + 前端**：`POST /task` SSE + 任务区视图（并列不混池；收尾回落；**不含**主/子焦点切换） | 中 | 中（端点 pytest + 前端 build/冒烟）—— 实为 **+3 例 / 1542 ⇒ 1545 passed** |
   | **C** | ✅ **已落地**（change `0123` / ADR-0116）：**E50 策略层**（规格最重）：ADDED 条款 + `plan_to_dict`/`plan_from_dict` + `max_concurrency` 接线 + `configuration` 键 | 大 | 高（打桩 planner 后可断言）—— 实为 **+44 例 / 1545 ⇒ 1589 passed** |
   | **D** | ✅ **已落地**（change `0124` / ADR-0117）：**E52 CLI 只读详情 + 实时状态**：`subtask_progress` 落子任务展开区（复用动作行友好名，不暴露内部 id/参数）+ 运行态徽标 `⟳`；「进入会话/焦点切换」**不在本 change** | 小 | 高（**订正**：headless Textual 基建**已存在**，非「无测试基建」）—— 实为 **+4 例 / 1589 ⇒ 1593 passed** |

3. 每 change 走本仓惯例：规格先行 → 测试先行（红→绿）→ 实现 → 四门禁 → 手工归档 → 单次提交。
4. 完成后回填 `README.md` §2 状态列。

## 7. 登记（本次评审新增，2026-10-06）

- **E55 主 loop 丢弃多余 `tool_call`**：`planner.py:222-225`（`Action` 为**单工具协议**，注释明写「并行多调用取首个」）。已坐实（§0.5.1），但修它须改 **L3 协议面**，成本独立于本 Phase 其余部分之和 ⇒ **不在本 Phase 落地**，登记待议。
- **调研报告不可达（E9 型）**：`temp/research/orchestration_parallelism_survey.md` 不在仓库 ⇒ E50 判据来源须**固化**（本文件 §0.5 已部分承载；§0.5.2 框架对比表仍缺出处）。
- **红线补充两条新口径**：① 子 agent 事件 `payload` **白名单化**（守「密钥只引用不读取、绝不进日志/记忆/事件面」）；② E52 若要给子 loop 接转录，**须先裁决**与 change `0115`「转录只注入主 loop」边界的冲突。
- **本 Phase 不重复/不触碰**：`tools.delegate` 阻塞 await 语义（§5）、phase 28 转录边界（除上述 ②）、phase 27 原生执行器。
