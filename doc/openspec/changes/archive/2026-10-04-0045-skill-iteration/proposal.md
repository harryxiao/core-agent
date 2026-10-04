# Proposal: 技能迭代闭环（skill iteration）

## Why

Phase 18 #8（维度1 技能库全自动进化的第三环，收口「日常任务→SOP→Skill→**持续迭代**」）。

1. **命中从未真正发生**：#6 提炼出 `Skill.instructions`（SOP 步骤），但 planner 注入 prompt 的
   只有**技能 id 字符串**（`runtime.py` 的 `skill_router=lambda task: [m.skill.skill_id ...]` →
   `planner._skill_hints` → 「可用技能：- skills.sop.xxx」）。**`instructions` 从未进入 prompt**
   ——「下次类似任务直接参考 skill 省 token」（phase-18 §1）在生产未兑现；这也使「迭代改写
   instructions」在运行时**不可观测**（无消费者）。
2. **无命中/结果记录**：技能是否被用上、用后成不成，全无累计（`SkillRouter.misses` 只记未命中
   的任务文本）。没有反馈，就无从判断一条 SOP「不完善」。
3. **无迭代闭环**：`VersionManager`（灰度/A/B）与 `ABResult` 已存在但**未接 runtime**（ADR-0048
   决策 ⑥ 记录了这一点），`Skill.version` 永远停在 `v1`；skills spec 的「版本管理与灰度/A/B」
   Requirement 只有 GIVEN/WHEN/THEN 的场景，**没有任何触发者**。

## What Changes

- **ADDED Requirement: 技能命中注入（skill hint injection）**——命中技能的 `id + 版本 +
  instructions 节选`（字符上界）注入推理 prompt；载荷为**纯 dict**（loop 不依赖 skills 类型）。
- **ADDED Requirement: 技能执行反馈（skill execution feedback）**——按 `(skill_id, version)`
  累计「命中」与「成功/失败」，供迭代判定；仅进程内，不影响本轮结果。
- **ADDED Requirement: 技能迭代闭环（skill iteration）**——失败率达阈值且样本达下限 → 注入的
  改写器（DI，缺省不启用）重写 `instructions` 为新版本 → `VersionManager.promote` 灰度 →
  双版本样本齐备后 `VersionManager.ab_test`（指标 = 各版本成功率）定夺：提升落地、退化丢弃草稿
  （**不**把技能置 `deprecated`）；落地登记可逆效应。
- 新增 `src/core/skills/feedback.py`（`SkillFeedback` / `SkillStats`）与
  `src/core/skills/iteration.py`（`SkillIterator` + `build_iterate_prompt`）。
- `SkillRouter` 增命中快照渲染（`skill_hint`：id/版本/instructions 节选，`_MAX_HINT_CHARS`）。
- **loop 收尾钩子契约扩展**：`SopObserver(task, steps)` → `TurnObserver(task, steps, ok)`
  （成功与失败都提交；`SopExtractor.observe(ok=False)` 仍只吸收成功）——失败信号是「结果不达标」
  的唯一来源。
- `planner._system_prompt` 的技能块渲染由 `- <id>` 升级为 `- <id>（<版本>）：<步骤节选>`。
- `build_runtime`：构造 `SkillFeedback` / `SkillIterator`（复用 `VersionManager`，指标函数读
  反馈成功率）并接线主/子 planner 的命中钩子与 loop 的收尾钩子。

## Non-goals

- **多版本持久化 / 版本库**：草稿版本只存在 `SkillIterator` 进程内（落地才写回 `Skill`）；
  技能库与反馈均不落盘（先于本变更存在的缺口）。
- **失败轨迹入库**：改写 prompt 只带「现行 instructions + 命中/失败计数」，不喂失败轨迹原文
  （成本与隐私面）；「为什么失败」的定位归维度2 的 diagnose。
- **cooldown / 迭代轮数上限**：本批只做「新版本 = 当前版本号 +1」的单一迭代路径。
- **`SkillCrystallizer` 结晶（L3→L1）**：#10 auto-dissolve 的范围。

## Impact

- 规格：`skills/spec.md`（+3 Requirement）。loop spec 未提及命中钩子（#6 亦只在接口文档记录）
  → **loop 侧无规格 delta**（契约变更落 loop-interface.md + ADR）。
- 代码：新增 `src/core/skills/feedback.py`、`src/core/skills/iteration.py`；
  `src/core/skills/router.py`（命中快照）、`src/core/loop/planner.py`（渲染 dict 载荷）、
  `src/core/loop/default.py`（`turn_observer` 契约）、`src/core/runtime.py`（装配 + 接线）。
- 契约：`doc/03-interfaces/skills-interface.md`（§4 命中快照 / §3 VersionManager 接 runtime）、
  `doc/03-interfaces/loop-interface.md`（钩子改名 + ok 位 + 技能块渲染）、ADR-0050。
- 兼容性：`SkillRouter.match` 不变；`LLMPlanner(skill_router=...)` 的回调**返回类型变**
  `list[str]` → `list[dict]`（生产唯一调用方是 runtime 闭包，测试同步）；未注入
  feedback/iterator 时行为与今天逐字节一致。

## Risks

- **误触发迭代**（低质量反馈驱动改写）：样本下限 + 失败率阈值 + 缺省不注入改写器；迭代结果仍
  经 A/B 定夺，退化即丢弃。
- **token 成本**：命中注入按 `_MAX_HINT_CHARS` 截断；迭代改写每「反馈不达标」一次模型调用。
- **A/B 指标口径**：指标是**成功率**（本进程内样本），样本少时噪声大 → 以下限门控；跨进程
  持久化样本不在本次范围（如实记录）。
