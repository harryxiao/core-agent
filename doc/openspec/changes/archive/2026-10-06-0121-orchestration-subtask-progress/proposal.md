# 提案 — 子任务运行态实时回流（change 0121 / phase-29 change A：E51）

## 背景

`coding-plan/phase-29.md` 立账的编排可见性缺口 **E51**（用户需求②「串行/并行都需 CLI + web/app 动态显示
子 agent 主题 + 运行状态」的**数据面**）。phase-29 §6 已裁决把该 Phase 拆为 A/B/C/D 四个 change，本
change 是最小的 **A：事件回流**（后续 B=HTTP 面 + 前端、C=E50 策略层、D=CLI 只读呈现面）。

| # | 一手事实（2026-10-06 复核，行号已核实） | 后果 |
|---|---|---|
| 1 | `scheduler.py:398-401` `result = await profile.loop.arun(goal)` —— 子任务**只取终态** `LoopResult` | 子 Agent 的动作/步进中间态在编排层**被吞**（E51 根因） |
| 2 | `scheduler.py:35` `Emit = Callable[[LoopEvent \| None], None]` **已是** `_run_subtask` 形参（`:346`）、`_fan_out` 已透传（`:321`）、`run` 已排水（`:206-215`） | **外送通道已建好**，回流不需要新通道（订正 phase-29 §0.6 首行） |
| 3 | `api.py:189-196` `UIAPILayer.run_task` 已把编排事件映射为 `task.*` SSE | 消费面**已存在**（HTTP 暴露与前端属 change B） |
| 4 | `loop/protocol.py:105` `astream` **已在 `LoopPlugin` 协议上**；`AgentProfile.loop` 即 `LoopPlugin \| None` | 流式入口**不重复造**；`DefaultLoop.arun` 本就是 `astream` 的三态归一（`default.py:212-224`） |
| 5 | `default.py:216/267/385` `astream` 实际产出 `loop_started` / `reply_delta` / `action_started` / `action_completed` / `step_completed` / `loop_finished` / `loop_failed` | 里程碑事件名**以代码为准**（`reason_started` 不存在，订正 phase-29 §0.6 第二行） |

**契约面现状（能力缺口，非缺陷）**：`orchestration` spec `:193` 的进度事件词表已含 `subtask_started` /
`subtask_completed`，但**无「运行态」事件** ⇒ 「动态显示运行状态」在**编排层可观测面**上是空白（CLI/Web
今天只能看到「开始 / 完成」两个离散点）。按本仓 SDD 惯例 **规格先行**（非 `skip_specs`）。

## 变更目标

**`orchestration/spec.md` 「任务入口与进度事件」Requirement MODIFIED**（在既有词表上补一个事件与三条口径）：

1. **新增 `subtask_progress` 事件** —— 子任务 SHALL 经子 Agent 循环**流式接口**执行，其**里程碑事件**
   （动作开始 / 动作完成 / 步进完成）SHALL 实时外发为 `subtask_progress`（带 `task_id` / `subtask_id` /
   内层事件类型 / 白名单载荷 / 时间戳），走编排器**既有**通道（不另建旁路）。
2. **粒度与白名单** —— 只回里程碑；模型流式**原文** `reply_delta` **不回流**（洪泛 + 暴露未定稿原文）；
   载荷**按内层事件类型白名单化**（逐类只带已知字段），白名单**外**的类型（含未来新增）不外发；
   凭据不进事件面（守「密钥只引用不读取」）。
3. **附加通道、终态不变** —— 终态仍归一为 `SubtaskOutcome`，fan-in / 依赖交接 / 波次推进判据不变；
   无里程碑时行为与回流前**逐字一致**。

## Non-goals

- **不建新通道**：复用 `Emit` → `run` 排水 → `run_task` 映射（事实 2/3）。
- **不改终态语义**：`DefaultLoop.arun` 的「三态归一」对 `delegate` 等调用方**逐字不变**。
- **不动 HTTP 面与前端**（`POST /task` SSE 路由、任务区视图 = phase-29 **change B**）。
- **不动 CLI/TUI 呈现**（折叠块展开细节 = phase-29 **change D**）。
- **不动 E50 调度策略**（难易度 / `max_concurrency` 接线 = phase-29 **change C**）。
- **不动主 loop 多 `tool_call` 丢弃**（phase-29 §7 **E55**，须改 L3 协议，独立登记）。
- **不改 `subtask_started` / `subtask_completed` 载荷**（下游消费面已依赖其形状）。

## 判据与取舍（判据订正 2 条）

**(a) 内层键名取 `event` / `data`，不取 phase-29 §3.2 草记的 `event_type` / `payload`。**
后者会造出 `LoopEvent.payload["payload"]` 的嵌套同名（`LoopEvent` 自身字段就叫 `payload`），
读侧要写 `event.payload["payload"]["…"]` —— 易错且不可读。取 `event` / `data` 后读侧为
`event.payload["data"]["tool_id"]`。此为**键名订正**，不改变信息面。

**(b) 终态归一**抽为 `core/loop` 的**共享实现**（`collect_result`），而非在 `scheduler` 内重写一遍。**
`DefaultLoop.arun`（`default.py:212-224`）与 `scheduler` 现在需要**同一套**「`loop_finished` 取载荷 /
`loop_failed` 归 `failed=True` 且回复取 `reason` / 未达终态不抛」语义；两处各写一遍必然漂移（新增终态
事件类型时只改一处）。抽为**纯函数**后 `arun` 改为其薄壳（**两处调用点**，非单次使用 = 不违「不为单次
使用造抽象」）。**不**把该函数放进 `LoopPlugin` 协议（不得迫使所有实现新增方法）。

**代价如实登记**：本 change 使 `scheduler` 由 `arun` 改走 `astream` ⇒ **3 处测试替身**（`test_phase14.
_FakeLoop` / `test_phase15._FakeLoop` / `test_session_isolation._SessionRecordingLoop`）须从
`arun` 迁到 `astream`；**不提供「无 `astream` 则回落 `arun`」的兜底** —— `astream` 是 `LoopPlugin`
**协议成员**（事实 4），给非协议替身留兜底等于为测试留生产分支（`_reason_events` 的 planner 降级
不属此列：那里 `planner=` 是**公开可注入**的裸 callable，确有非流式实现）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 事件洪泛（每个子任务每个动作一条） | 只回**里程碑**（3 类）+ **显式排除** `reply_delta`；量级受循环轮数上界约束 |
| 载荷泄露凭据 / 原始输出 | **白名单化**（逐类只带已知字段，未知类型不外发）；内层 `args` / `output` 已由 `default.py` 的摘要函数截断 |
| 改走 `astream` 打断既有替身 | 3 处替身**显式迁移**（迁移处集中、可审）；`DefaultLoop` 系替身天然继承 `astream`，零改动 |
| `collect_result` 抽取改动 `arun`（热路径） | 纯机械搬运，语义逐字保留；`arun` 回归由既有 loop / delegate / pet / beast 用例覆盖 |
| 回流改变 fan-in 判定（把进度当结果） | 事件与终态**分流**：`subtask_progress` 只 `emit`，结果仍由 `astream` 归一后的 `LoopResult` 决定（有场景守门） |

## 兼容性

- `subtask_started` / `subtask_completed` / `task_finished` / `task_failed` 载荷**零变更**（只**新增**一类事件）。
- `DefaultLoop.arun` / `astream` 的**签名与事件序逐字不变**（`arun` 只是改由 `collect_result` 实现）。
- `TaskScheduler.run` 的**抛出语义与返回值**不变（`run` 只认 `task_failed` / `task_finished`，新增事件被忽略）。
- `Emit` / `_fan_out` / `run` 排水结构**零改动**。
