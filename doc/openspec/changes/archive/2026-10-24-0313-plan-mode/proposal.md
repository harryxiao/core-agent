# Proposal — 产品入口模式对齐：plan 模式、`/task` 收敛与单子任务自跑（甲-2）

## Why

对照 `agentic-os/sdd/Agent_Workflow_Specification-3.md` §五「视角四 产品入口模式」与本仓现状：

1. **`/task` 是用户入口，与「delegate 内置不暴露」相悖**：外部规格的 `delegate` 是**装配期启用**
   的内部路径（`createDelegateFlow`），用户可见模式只有 `quick`（缺省）与 `plan`；本仓 TUI
   却把 `/task` 直接暴露为编排入口 —— 用户绕过计划与审批直接进多 Agent 派发。
2. **plan 模式缺失**：用户无法「先只读勘察、产出可审阅计划、批准后按 quick 权限继续」。
3. **单子任务仍经能力路由**：外部规格的 `selfRunSingleTask`（甲-2）是「计划只有一个子任务 ⇒
   由发起方主 Agent 自跑」；本仓 `TaskScheduler` 对所有子任务无条件 `router.match` 后派给子
   Agent —— 单任务目标多一次跨 Agent 交接与上下文重建，且可能因能力词元无命中判
   `NO_AGENT_MATCH`。

**用户裁决**（2026-10-24）：`收敛，甲-2 自跑本轮做，plan 的审批工件落在会话内临时 PlanDraft`。

## What Changes

- **会话级执行模式**：每个会话维护 `agent_mode ∈ {quick, plan}`（缺省 `quick`；进程内临时
  状态，不落注册表、不跨进程）。TUI 新增 `/plan` / `/quick`；计划模式下一条消息走**计划轮**。
- **计划轮只读**：以**主 Agent 循环**的**只读工具面**（仅 `READ` 级工具，显式排除
  `tools.delegate`）执行勘察；随后复用编排器拆解产出**计划草案**。
- **临时 `PlanDraft`**：会话内、进程内、同一会话至多一份；记录草案标识 / 目标 / 子任务 DAG /
  波次 / 成功标准 / 勘察结论。不落盘、不新增状态文件。
- **y/n 审批**：`y` 在同一会话按**与 quick 相同的执行权限**执行已批准计划（不重拆、不自动
  升级 delegate），`n` 丢弃；两种结果都回到 `quick`。
- **`/task` 收敛**：移除 TUI `/task` 用户入口（CLI `core-agent task` 保留为操作面）；
  TUI 的编排事件呈现（子任务折叠块 / 标签栏 / 焦点视图）改由**计划批准后的执行流**驱动。
- **单子任务自跑（甲-2）**：`TaskScheduler` 接受可选 `self_loop`；执行显式声明 `self_run`
  且计划恰好一个子任务时，经**统一 `TaskHandoff`** 直接交给主 Agent 循环，不经路由匹配。
  缺省不声明 ⇒ 行为逐字不变；计划多子任务 ⇒ 忽略声明走既有路由；未注入 `self_loop` ⇒
  回落既有路由（不使任务失败）。

## Impact

- 规格：`ui` MODIFIED ×1 + ADDED ×1；`orchestration` MODIFIED ×1 + ADDED ×2（自跑 / 计划草案）。
- 代码：`src/core/orchestration/scheduler.py`（`draft_plan` / `self_loop` / `self_run`）、
  `src/core/orchestration/handoff.py`（不改，仅复用 `stream_handoff`）、
  `src/core/tools/provider.py`（`subset` 视图）、`src/core/ui/plan.py`（新）、
  `src/core/ui/api.py`、`src/core/ui/errors.py`、`src/core/ui/repl.py`、`src/core/runtime.py`、
  `src/core/entry.py`。
- 行为：缺省（quick、无 `self_run`）下 **prompt / 工具面 / 路由 / 事件面逐字不变**；CLI `task`
  与 Web `/task` 端点不变。
- 配置：**零新配置键**。

## Out of Scope（明确不做）

- **不为 Web 增加 plan 端点**：本轮只做 TUI 面；`agent_mode`/`PlanDraft` 为进程内会话状态，
  不宣称跨入口共享。
- **不做 `Tab` 切换模式**：`Tab` 已被命令浮层采纳占用，本轮只提供斜杠命令。
- **不持久化 `PlanDraft` / `agent_mode`**：草案是会话内临时工件（用户裁决），进程退出即失效。
- **不改能力路由为语义匹配**：Router 仍是既有词法打分；DAG 的 `replan` / `terminate` 仍由
  调度器内联判定。
- **不改 Web `/task` 与 CLI `task` 的入口语义**：二者分别作为 Web/操作面保留。
- **不实现 plan 模式的编辑后重提**（y/n 二选一；编辑需求留给后续）。
