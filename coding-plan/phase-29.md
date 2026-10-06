# Phase 29：orchestration 子 Agent 动态调度 + 运行态实时回流 + 会话导航

> **状态**：📋 待裁决（能力扩展**提案**，非纯缺陷账本；四处缺口 E50~E53，串行/并发**载体已存在**，缺的是「动态决策」与「可见性/可导航」两层）
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

## 1. 范围与定位

- **分层**：L3.5 `orchestration`（调度策略/事件回流）+ L7 入口 `ui`（repl / fastapi_serve / web_bridge）呈现与导航。
- **不在范围**：不新建子 Agent 执行载体（`DefaultLoop.arun` + `SubAgentProfile` 已存在）；不改 `tools.delegate` 语义（其阻塞 await 是「主 Agent 主动委派」的**有意设计**，与 `TaskScheduler` 波次并发是**两条正交通路**）。

## 2. 需求映射（4 缺口 → 落地件）

| # | 缺口 | 用户需求 | 落地方向 |
|---|---|---|---|
| E50 | 难易度动态决策 | 「依据任务难易度动态决策串行还是并行」 | `Subtask` 增 `difficulty` 字段（或难易度由 decomposer 评估写入）；`_build_waves` 之后的**调度策略层**按难易度决定同波次无依赖子任务「并发扇出 vs 串行逐个」；依赖拓扑仍为硬约束（有依赖必串行） |
| E51 | 运行状态实时回流 | 「动态显示子 agent 主题 + 运行状态」 | `scheduler` 改走 `loop.astream(goal)` 消费中间事件（`reason_started`/`action_started`/工具调用等），`emit(LoopEvent("subtask_progress", {...}))`；UI 订阅渲染 |
| E52 | 进入子 agent + 回主 agent | 「进入子 agent 查看详情，完成回到主 Agent」 | CLI：折叠块升级为**可进入的子会话视图**（子 agent 消息流 + 运行态）+ 显式「回到主 Agent」入口；Web：右栏任务栏 + 子 agent 面板 + 主/子切换 |
| E53 | web/app 任务栏渲染 | 「CLI 和 web/app 都动态显示」 | `fastapi_serve.py`/`web_bridge.py` 消费编排进度事件，渲染任务列表（子 agent 标题 + 状态徽标），点击进入详情、返回主会话 |

## 3. 落地拆解

> **顺序**：规格先行（E50 改 `orchestration` spec、E51 改事件契约、E52/E53 改 `cli-ops`/`ui` spec）→ 测试先行 → 实现 → 门禁四命令全绿。

### 3.1 E50 难易度动态决策（规格先行）
1. `orchestration/spec.md`：`Subtask` 增 `difficulty`（如 `"easy"|"medium"|"hard"` 或数值档）+ 调度策略条款（难易度 → 串行/并发阈值）。
2. `decomposer.py`：拆解时评估难易度写入 `Subtask.difficulty`。
3. `scheduler.py`：`_fan_out` 之前新增**调度策略**——高难度子任务串行（避免并发资源争抢/上下文污染）、低难度可并发；依赖拓扑仍由 `_build_waves` 保证。
4. 阈值/策略须**可配置**（`configuration` 键），缺省保守（难任务串行）。

### 3.2 E51 运行状态实时回流（事件契约先行）
1. 事件契约增 `subtask_progress`（含 `subtask_id`/`task_id`/`event_type`/`payload`/`ts`）。
2. `scheduler.py:399-401` 由 `arun` 改为 `async for event in profile.loop.astream(goal)`，把中间事件转译 emit；终态仍归一为 `SubtaskOutcome`。
3. `DefaultLoop.arun` 保持「三态归一」不变（供 `delegate` 等需要终态的调用方），**新增** `astream` 已存在，不重复造。

### 3.3 E52/E53 会话导航 + 任务栏（消费面接线）
1. `repl.py`：`_open_subtask` 从只读折叠块升级为**子会话视图**（子 agent 消息流 + 运行态徽标），加「回到主 Agent」切换。
2. `fastapi_serve.py`/`web_bridge.py`：转发 `subtask_*` 事件 → Web 右栏任务列表（标题 + 状态）+ 子 agent 详情面板 + 主/子切换。

### 3.4 门禁
- `ruff check/format` + `pyright` + `pytest -q` 全绿；`validate --all` 全绿（spec 改动须同步 interface 契约）。
- 新增单测覆盖：难易度→串/并策略、中间事件转发、会话切换往返。

## 4. 裁决点（须用户拍板后规格先行）

1. **E50 策略形态**：难易度档位（三档 `easy/medium/hard`）还是数值分（0~1）？阈值硬编码还是进 `configuration`？（建议：三档 + `configuration` 可配，缺省 hard 串行 / easy·medium 并发）
2. **E52/E53 交互范围**：CLI 子会话是「内嵌面板」还是「独立全屏视图」？Web 任务栏是否复用现有右栏会话列表（phase-28 `0116` 已落地）还是新建任务面板？
3. **E51 回流粒度**：中间事件全量回流（重）还是只回「里程碑事件」（reason 开始/工具调用开始/完成，轻）？（建议：轻量里程碑事件 + 终态，避免 web 端洪泛）

## 5. 去重边界

- **不重复** phase-28 E46/E47/E49（pet/beast 返回可见性、会话隔离、会话历史落盘回灌——那是**记忆/转录**维度，本 Phase 是**编排运行态**维度）。
- **不重复** phase-27 原生执行器（进化引擎维度）。
- **不重建** 串行/并发载体（`delegate` 阻塞 await + `TaskScheduler` fan-out 已存在，本 Phase 只补「决策策略」与「可见/导航」两层）。
- `tools.delegate` 阻塞 await **不改**（主 Agent 主动委派语义，与波次并发正交）。

## 6. 下一步

1. 用户对 §4 三处裁决点拍板（策略形态 / 交互范围 / 回流粒度）。
2. 裁决后按 §3 规格先行 → 测试先行 → 实现 → 门禁，一个 change 落地。
3. 完成后回填 `README.md` §2 状态列并 commit。
