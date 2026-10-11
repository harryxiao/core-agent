# Design 0197 — SOP 提炼新增任务级过程输入

## 1. 问题定位（P3）

| 面 | 事实 | 缺口 |
|---|---|---|
| `loop/default.py:113-135` | `_action_steps(ctx)` 只取**本轮**「工具（参数）→ 结果」行 | 无任务粒度的过程输入 |
| `skills/sop.py:81` | `observe(task, steps)` 以**任务文本**归组 | 长任务逐轮任务文本漂移 ⇒ 归组键漂移 ⇒ 永不达阈 |
| `orchestration/scheduler.py:290-292` | `DoneFn` 在**成功 `DONE`** 时调一次 | 现成接缝：与「只吸收成功轨迹」天然对齐（**未被利用**） |
| `runtime.py:955` | checkpoint `state["trace_ids"]` | 任务 → 各子任务 `loop.steps.<tid>` 的连接键（**未被利用**） |

## 2. 设计决策

### 2.1 采样单位 = 编排任务（用户裁决①）

`DoneFn` 签名 `(task_id, outcomes, plan, session_id)`；`plan.goal` / `plan.order` 提供任务文本与
子任务骨架；`outcomes` 各带 `trace_id` ⇒ 经 `_steps_lookup` 回读各子任务步序。**不**用
`SubtaskOutcome.reply`（截断 2000 字，不足以承载步序）。

### 2.2 样本隔离 = 第二个实例 + `namespace`（隔离是**正确性**要求，非锦上添花）

两路步序**语义不同**（任务级 = 子任务骨架；单轮 = 工具调用行）⇒ 混组会产出**浑浊 SOP**。隔离三面：

1. **样本集**：第二个 `SopExtractor` 实例，独立 `path`（`sop-task-samples.json`）；
2. **组键**：`namespace="task"` ⇒ 组键前缀化 `task::…`，**不**词法复用单轮技能的 `task_types`；
3. **`skill_id`**：`_skill_id_for(key)` 由前缀化组键算出 ⇒ 与单轮产物落**不同** id 空间。

缺省 `namespace=""` ⇒ 单轮路径**逐字不变**。

### 2.3 零效应读取（守 P2 / 承 `_failure_lookup` 范式）

`_steps_lookup(backend)` 走 `MemoryBackend.search("")`，**不经** `MemoryStore.read`（后者会强化
`reuse_count` 并落盘）⇒ **零写入、零效应**、且**层无关**（条目被 `forget` 迁 L4 后仍可读）。
条目在**写入时**已脱敏（`loop/default.py:830`）⇒ 新读取面**不引入**密钥暴露。

### 2.4 组合器（纯函数）

`compose_task_steps(plan, outcomes, lookup) -> list[str]`：按 `plan.order` 遍历子任务 id → 由
`outcomes` 取 `trace_id` → `lookup(tid)` 取回步序 → 渲染「子任务目标：… / 步序：…」行；总长
有上界（token 有界）。放在 `runtime.py` 组合根（依赖 orchestration 类型），**不**进 `skills/`
（skills 不 import orchestration）。

## 3. 规格落点

`skills`「SOP 提炼（skill extraction）」**MODIFIED**：既有 7 Scenario **逐字保留** + 「任务级过程
输入」bullet + 2 Scenario（任务达阈提炼 / 任务级与单轮不混组）。

## 4. 验证

- 红测试：任务级达阈入库（`task_types` 含 `task::…`）/ 与单轮不混组（`skill_id` 不同）/
  `_steps_lookup` 零效应（`reuse_count` 不变）/ 组键前缀确定性。
- 四门禁（直连二进制）；`openspec validate` → 手工归档（0 行丢失 / 0 Scenario 标题丢失）。

## 5. 已知局限（登记 `coding-plan/known-risk.md` §3）

- **续跑已 `DONE` 任务会二次触发 `_on_done`** ⇒ 同一成功轨迹被记两次样本（跨进程无去重面）。
  本 change **不**修（去重要读检查点，属另一缺陷面）。
- 任务级样本仍**受 `plan.order` 拓扑**；乱序 / 缺失 `trace_id` 的子任务步序被跳过（不炸）。
