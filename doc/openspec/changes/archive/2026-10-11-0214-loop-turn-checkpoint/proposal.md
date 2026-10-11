# Proposal 0214 — 主循环会话轮级检查点（`turn.<trace_id>`）

## 为什么

六能力走查确认：`create_checkpoint` 的生产**唯一**调用链是**编排器波次回调**
（`runtime.py` 的 `_checkpoint` / `_finalize` → `_write_checkpoint`）⇒ 检查点只覆盖**编排任务**
的波次边界。后果：

- **长时的单轮**（非编排：一次对话轮里跑很多工具步）被杀 ⇒ **整轮丢失**、重启后**无任何呈现**
  —— 用户既看不到「上次有轮被打断」，也没有任何在途痕迹（会话转录只记 user/assistant 两行，
  中间步序全无）。
- 与「退出重启恢复动态记忆」能力相对照：记忆侧已有多层耐久（`memory.jsonl` 原子化 `0206`、
  恢复扫描全覆盖 `0207`、保留策略 `0208`），而**执行态轮级**是缺口。

## 做什么

### 1. `DefaultLoop` 新可选参 `turn_checkpoint`

- `turn_checkpoint: Callable[[str, str, str, bool], None] | None = None`
  （`(trace_id, session_id, goal, done)`；沿 `turn_observer` / `cold_path` 闭包注入先例
  ⇒ loop **不 import** `durability`）。
- **两个写点**：轮首（感知完成后）写 `done=False`；轮末（`remember` 之后）写 `done=True`。
  成功与「达上限终止」两路都到得了轮末 ⇒ 终止轮也被标记完结。
- `astream` **无 try/finally** ⇒ 中途异常 / 被杀天然留 `done=False`（镜像编排波次语义）。
- **不逐步刷新**：`CheckpointStore._persist` 每次 `put` 全量重写 ⇒ 逐步写是 O(n²)；
  增长由 `0208` 保留策略兜（故 `0208` 先行）。

### 2. 组合根闭包（主 loop **专属**）

- `checkpoints.create_checkpoint(task_id=f"turn.{trace_id}", session_id=…,
  state={"kind": "turn", "goal": …, "done": …})` —— **独立命名空间**防 `task --resume` 误接。
- **只注入主 loop**：子 Agent / 神兽 / 宠物 loop **不接**（沿既有隔离注记 —— 会话维度是主
  Agent 的门面概念，同 `transcript`）。
- 闭包**自防御**：持久化失败只告警降级，不冒泡进本轮。

### 3. 呈现隔离

- `_recover_incomplete`（`runtime.py`）按 `state["kind"] == "turn"` **分流**：轮级检查点
  **不**产生续跑句柄（`turn.` 命名空间不交给 `CrashRecovery.restore`）。
- 新增 `Runtime.recover_turns()` 返回未完结轮的 `(task_id, session_id)`。
- `_surface_incomplete`（`entry.py`）**扩一段**：任务面照旧提示 `task --resume`；轮面**独立呈现**
  （「上次有 N 个中断的会话轮（会话 …）」）且**不给**续跑提示 —— **续聊即恢复**，语义不同。

### 4. 配置 `loop.turn_checkpoint`（bool，缺省 `False`）

沿 `loop.block_plan` / `loop.causal_links` 先例（结构化段 ⇒ 非法取值阻断启动）。
缺省关 ⇒ 构造参 `None` ⇒ **零写入、逐字不变**。

## 不做（边界）

- **不含撤销账本**（`EffectTracker` 的 undo 闭包不可序列化 ⇒ 不做假耐久；`goal` / `rounds`
  快照**仅供呈现**、不供重放）。
- **不给轮级检查点接重放** —— 恢复语义仍是**显式**（守 P2：副作用不自动重放）。
- **不逐步刷新**（见上，O(n²) 与保留策略分工）。
- **不给子 / 神兽 / 宠物 loop 接**（隔离边界）。
- **不改会话转录**（轮级检查点是**执行态**留痕，不是对话历史）。
