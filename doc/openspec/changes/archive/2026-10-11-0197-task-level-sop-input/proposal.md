# Proposal 0197 — SOP 提炼新增任务级过程输入（task-level-sop-input）

## Why（缺口 G1）

用户 2026-10-11：「**Procedural 本质是基于长会话任务过程 — 提炼/验证/沉淀 — 的一套 SKILL/SOP/
工作流等技能资产**」。逐行取证确认：SOP 提炼**只接了单轮轨迹**——`_action_steps(ctx)`
（`src/core/loop/default.py:113-135`）只取**本轮**的「工具（参数）→ 结果」行。对**长任务**
（orchestration 任务跨多轮、每轮任务文本不同）而言：

- 每轮各自成一个样本 ⇒ 任务文本逐轮漂移 ⇒ 归组键漂移 ⇒ **永不达阈**（`_SOP_MIN_SAMPLES=3`）；
- 即使凑巧归组，单轮步序也**不含**子任务骨架 —— 提炼出的不是「任务过程 SOP」。

⇒ 缺的是**任务粒度**的观察面：以「**任务目标 + 子任务步序**」为单位，在任务**成功**收尾时提交。

## What Changes

**规格先行**（`skills/spec.md`「SOP 提炼（skill extraction）」**MODIFIED**）：新增 bullet
「**任务级过程输入**」（任务目标 + 按 `plan.order` 聚合的子任务步序；与单轮面**样本隔离**）
+ 2 Scenario（任务达阈提炼 / 任务级与单轮不混组）。既有 7 Scenario **逐字保留**。

**实现**：

- `src/core/skills/sop.py`：`SopExtractor.__init__` 增可选 kwarg `namespace: str = ""`；组键在
  namespace 非空时前缀化（`f"{ns}::{raw}"`）；缺省 `""` ⇒ **逐字不变**。
- `src/core/runtime.py`：新增 `_steps_lookup(backend)`（与 `_failure_lookup` 同形，**零效应**
  读 `loop.steps.<trace_id>`）；构造**第二个** `SopExtractor`（同库、异样本文件
  `sop-task-samples.json`、`namespace="task"`）；`_finalize` 内装配 `compose_task_steps(...)`
  并 `observe(plan.goal, steps, ok=True)`。

## Impact

- **规格**：`skills`（MODIFIED ×1「SOP 提炼」+2 Scenario）。canonical `skills` scen **45 → 47**、
  req **10 不变**。
- **代码**：`skills/sop.py`（+1 可选 kwarg + 组键前缀化）；`runtime.py`（`_steps_lookup` +
  第二实例 + `_finalize` 接线 + `compose_task_steps`）。
- **测试**：+4 新增（任务级达阈入库 / 与单轮不混组 / `_steps_lookup` 零效应 / 组键前缀确定性）。
- **安全**：消费的是**写入时已脱敏**的 `loop.steps.<trace_id>`（`loop/default.py:830`
  `redact_secrets`）⇒ **不引入**新的密钥暴露面。
- **不做**：**不改写**现有单轮采集路径（本 change 只**新增**任务级入口）；质量门归 change 0198；
  workflow 结构化资产 / 技能→插件结晶 / L3 记忆层统一 **本批不做**。

## Non-goals

- 质量门（change 0198）；`Skill` 新增结构化 steps 字段；`SkillCrystallizer` 接线。
- 续跑已 `DONE` 任务的 `_on_done` 二次触发去重（属另一缺陷面，登记为已知局限）。

## 风险

- **同步回调 hazard**：本 change 的接线落在 `_on_done` 内 ⇒ 已由 change 0196 卸载出事件循环
  （`await asyncio.to_thread`），模型调用**不**阻塞事件循环。**0196 是本 change 的前置**。
