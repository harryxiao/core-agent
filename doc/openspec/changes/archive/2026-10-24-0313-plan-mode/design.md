# Design — plan 模式、`/task` 收敛与单子任务自跑（0313）

## 1. 目标与不变量

**目标**：把用户可见入口收敛为 `quick`（缺省）/ `plan` 两模式，`delegate` 只作为内部执行路径；
plan 批准后的执行走同一编排器，单子任务由发起方主 Agent 自跑（甲-2）。

**不变量**（缺省路径逐字不变）：

1. `quick` 模式下 `run_loop` / 工具面 / prompt / 事件面与 change 0312 时点一致。
2. `TaskScheduler.astream(..., self_run=False)`（缺省）对所有计划走既有路由；`self_loop`
   未注入时 `self_run` 回落既有路由。
3. 编排器的验收 / 重试一次 / 重拆一次 / 检查点 / token 预算 / 取消语义**不因自跑改变**。
4. `PlanDraft` / `agent_mode` 零落盘、零新配置键、零新第三方依赖。
5. 密钥只引用不读取：草案与事件面只含目标 / 子任务 / 验收文本，勘察结论文本不进事件载荷。

## 2. 组件与数据流

```
TUI /plan ──► UIAPILayer.set_agent_mode(session, "plan")
                  │
用户消息 ─────────┤ agent_mode == plan
                  ▼
        UIAPILayer.run_plan_turn(session, text)
          1. plan_loop.astream(text)      ← 只读工具面（READ only，无 delegate）
          2. 累计 loop_finished.reply      ← 勘察结论（仅在内存）
          3. orchestrator.draft_plan(text, context=勘察) → Plan
          4. PlanSessions.put(PlanDraft)   ← 会话内临时工件
          5. yield plan.draft_ready        ← 目标/子任务/依赖/验收（不含勘察原文）

用户 y ──► UIAPILayer.approve_plan(session, draft_id)
          1. PlanSessions.take(draft_id)   ← 一次性消费，防重放
          2. set_agent_mode(session, "quick")
          3. orchestrator.astream(task, goal, plan=draft.plan, self_run=True)
                                              ← 计划含 1 个子任务 ⇒ 主 Agent 自跑（甲-2）
用户 n ──► UIAPILayer.discard_plan(session, draft_id) + 回 quick
```

### 2.1 只读工具面（plan_loop）

- 装配期由组合根构造**第二个 `DefaultLoop`**（同 memory / transcript / tracer / gate / approver
  / planner 配置），唯一差异是 `ToolProvider` 换成**子集视图** `tools.subset(readonly_ids)`。
- `readonly_ids` 判定：对每个已注册工具调 `PolicyEngine.classify(tool_id, "", coeffects)`，
  仅保留 `RiskLevel.READ`；再**显式排除** `tools.delegate`（`classify` 对
  `agent:delegate` 有字面量只读豁免，但 plan **SHALL NOT** 自动升级为 delegate）。
- 子集视图共享同一 resolver / tracker / gate / approver（零语义分叉）；未登记工具在
  `ainvoke` 处即返回「未知工具」⇒ **执行面**也阻断，不只靠 schema 隐藏。
  被排除工具即使被模型幻觉调用也 fail-closed。

### 2.2 草案产出（`TaskScheduler.draft_plan`）

```python
async def draft_plan(self, goal, success_criteria=None, *, context="") -> Plan
```

- 拆解输入 = `goal` +（非空时）`\n\n【只读勘察结论（供拆解参考）】\n` + `context`
  （`context` 截断到 `MAX_HANDOFF_CHARS`，与交接字段同一上界）。
- 拆解后**还原 `plan.goal = goal`**（勘察上下文不得成为执行目标）。
- **零执行副作用**：不写检查点、不写 trace、不动进度跟踪器；仅一次 `decomposer.decompose`。
- 复用既有 `LLMSubtaskPlanner`（1–6 子任务、验收标准、依赖、优先级、难度），不新增第二个
  planner，避免两套拆解口径。

### 2.3 单子任务自跑（甲-2）

`TaskScheduler` 新增：

- 构造参数 `self_loop: LoopPlugin | None = None`（缺省 `None`）。
- `run(..., self_run: bool = False)` / `astream(..., self_run: bool = False)`，沿
  `_stream_task → _execute_wave → _stream_wave → _fan_out → _run_subtask` 显式透传
  （与 `attempt` / `previous` 同型；不引入实例级可变标志，避免并发任务串味）。

`_run_subtask` 的执行者解析改为：

```python
loop = self._self_loop if (self_run and len(plan.subtasks) == 1) else None
if loop is None:
    loop = router 匹配到的 profile.loop（沿用既有 NO_AGENT_MATCH 分支）
stream = stream_handoff(loop, handoff, deadline=handoff.deadline)
```

- **自跑判定只看计划规模**（`len(plan.subtasks) == 1`），与子任务 `difficulty` /
  能力词元无关；多子任务忽略 `self_run`。
- `router.handoff_stream(...)` 改为直接 `stream_handoff(loop, handoff)`：二者本就是
  `resolve + stream_handoff`（`router.py:60-63`），正常路径取到的是同一 `profile.loop`，
  行为逐字一致。
- 自跑的验收 / 失败重试 / 重拆 / 检查点 / 预算 / 取消分支**不新增任何分支** —— 执行流汇入
  同一 `collect_result` 与后续管道。
- 主 loop 的会话归属：`handoff.session_id` 已由 `_build_handoff` 填发起会话 ⇒ 自跑的
  轨迹 / 记忆落在**发起会话**（与子 Agent 路径同口径）。

### 2.4 会话状态（`src/core/ui/plan.py`）

```python
PlanDraft: draft_id / session_id / goal / plan / exploration / created_at
PlanSessions:
    mode(session_id) -> "quick"（缺省）
    set_mode(session_id, mode)         # quick|plan，非法值 UI_PLAN_MODE_INVALID
    put(draft)                         # 同会话覆盖旧草案
    get(session_id, draft_id) -> PlanDraft | None
    take(...) / discard(...)           # 一次性消费 + 回 quick
```

- 进程内 dict，按 `session_id` 分桶；**不落盘**、不写注册表（注册表仍只承载标识 / 入口模式）。
- 同一会话至多一份草案：`put` 覆盖即视为旧草案作废（防误批准过期计划）。
- 草案标识 = `draft-<uuid8>`，只用于本进程内的 y/n 回执，不进入事件以外的持久面。

### 2.5 UIAPILayer 接口

| 方法 | 语义 | 失败 |
|---|---|---|
| `agent_mode(session)` | 读模式（缺省 quick） | 未登记会话 ⇒ `UI_SESSION_NOT_FOUND` |
| `set_agent_mode(session, mode)` | 置模式 | 非法值 ⇒ `UI_PLAN_MODE_INVALID` |
| `run_plan_turn(session, text)` | 只读勘察 + 草案，流式 loop 事件 + `plan.draft_ready` | 未注入 plan loop / 编排器 ⇒ `UI_PLAN_UNAVAILABLE`；拆解失败 ⇒ `UI_PLAN_DRAFT_FAILED` |
| `approve_plan(session, draft_id)` | 消费草案并按批准计划执行（`self_run=True`） | 草案不存在 / 非本会话 ⇒ `UI_PLAN_DRAFT_NOT_FOUND` |
| `discard_plan(session, draft_id)` | 丢弃草案并回 quick | 同上 |

- `approve_plan` 在开始执行**前**就回 `quick`：执行失败也不把会话留在 plan。
- 事件类型：loop 事件沿用 `_map_event` 既有映射；草案事件为 `plan.draft_ready`，载荷
  `{draft_id, goal, subtasks:[{id, goal, acceptance, depends_on}], waves, success_criteria}`。
- `run_plan_turn` 要求会话处于 plan 模式（否则 `UI_PLAN_MODE_INVALID`）—— 防调用方绕过 `/plan`。

### 2.6 TUI

- 命令真源 `_COMMANDS`：删 `/task`，增 `/plan`（"进入计划模式"）与 `/quick`（"返回快速模式"）。
  两者走专用分发分支（非只读 `handler`），忙态沿用既有拒绝。
- 计划决策输入：新增 `_plan_future` / `_plan_draft_id`。`on_input_submitted` 次序：
  工具审批 → 计划审批 → 浮层采纳 → 忙态 → `/resume` → 只读命令 → 普通消息。
  计划审批挂起期间 `_refresh_palette` 一并收起浮层（与工具审批同口径）。
- 计划轮渲染复用 `_run_turn` 的事件处理：抽出 `_handle_turn_event(event)`（纯呈现分支，
  无状态迁移），`_run_turn` 与 `_run_plan_turn` 共用。
- 草案呈现：目标 + 每个子任务的 `goal` / 依赖 / 验收标准（Markdown 列表），随后
  `y 批准执行 / n 放弃计划`。批准后的事件流走既有 `_add_task_widget`（折叠块 / 标签栏 /
  焦点视图全部复用）。
- 模式可见性：输入框 placeholder 在 plan 模式改为「计划模式：发送消息以只读勘察并产出计划
  草案」；`/plan` `/quick` 各给一行提示。不新增 chrome 行（守 0299 密度预算）。
- 欢迎语与 placeholder 中的 `/task` 文案同步移除。

### 2.7 组合根

- `Runtime` 增 `plan_loop: DefaultLoop`；`build_runtime` 以同一工厂构造主 loop 与 plan loop。
  工厂化只搬运既有关键字参数，不改变主 loop 语义。
- `TaskScheduler(..., self_loop=loop)`；`_build_ui` 注入 `plan_loop=runtime.plan_loop`。
- CLI `task` / Web `/task` 仍调 `astream(..., self_run=False)`（缺省），行为不变。

## 3. 备选方案与被拒理由

| 备选 | 被拒理由 |
|---|---|
| 用根 loop + 每轮工具白名单（`LoopContext` 过滤） | 需改 `LoopPlugin` 协议与全部循环实现；且执行面仍需拦截，等于在循环里复制一遍工具面逻辑 |
| plan 模式做成 permission mode | permission 模式是装配期固定的权限口径；plan 是会话级产品模式，二者正交（plan 执行要用 quick 权限） |
| `PlanDraft` 落盘 / 入记忆 | 用户裁决为「会话内临时工件」；落盘引入生命周期、清理与隐私面 |
| 批准后自动走 delegate（多 Agent） | 外部规格明文「plan 不自动升级为 delegate」；批准后按 quick 权限、单任务自跑 |
| 单任务也走路由，仅在 router 里注册主 Agent 画像 | 仍会经能力打分，词元无命中时可能选中别人；甲-2 的语义是**确定性自跑** |
| 自跑用实例级标志 | 并发任务共享调度器实例 ⇒ 串味；显式参数透传与 `attempt` 同型 |

## 4. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 计划轮工具面误含写工具 | 子集视图在 `ainvoke` 处 fail-closed；测试断言写工具不在 `active_tools()` 且调用返回未知工具 |
| plan loop 与主 loop 分叉（记忆 / 轨迹 / 会话） | 同一工厂构造、共享 memory / transcript / tracer / gate；仅 `ToolProvider` 不同 |
| 草案泄漏勘察原文 | 事件载荷只取结构化计划字段；测试断言载荷无 `exploration` |
| `/task` 移除破坏既有 TUI 测试 | 同步改断言（命令真源 / 欢迎语 / 分发）；CLI `task` 测试不动 |
| 自跑改变单任务 CLI 行为 | `self_run` 缺省 False；CLI 不传 ⇒ 路由路径逐字不变 |
| 批准后执行失败把会话卡在 plan | `approve_plan` 先回 quick 再执行 |
