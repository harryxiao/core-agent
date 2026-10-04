# Proposal: SOP 提炼（skill extraction）

## Why

Phase 18 #6（维度1 技能库全自动进化的第一环）。走查确认：

1. **`SopExtractor` 全仓不存在**（`grep Sop|extract` 无命中）——技能只有「注册 / 路由 / 版本」三段，
   **没有任何产生技能的入口**；`SkillLibrary` 在生产恒为空，`SkillRouter` 的匹配永远落空并
   把任务记为 miss（M3 遗留：miss 只沉淀、不复用）。
2. **skills spec 没有对应 Requirement**：`skills/spec.md` 只有「原子技能库 / 版本管理与灰度 /
   技能路由」三条，SOP 提炼属**新增能力**（phase-18 §6「契约对齐」明确要求回填接口文档）。
3. 这正是 phase-18 定位的「下次类似任务直接参考 skill **省 token**」的核心来源：没有提炼，
   技能库永远是空壳，维度1（SOP 全自动进化）无从谈起。

## What Changes

- **ADDED Requirement: SOP 提炼（skill extraction）**——同一类任务的**成功**轨迹累计达阈值后，
  由注入的提炼器把「任务 + 行动/结果序列」提炼为一条 `Skill`（`instructions` = SOP 步骤、
  `task_types` = 归组键），经 `SkillLibrary.register()` 入库（复用既有 schema 校验），并按
  「维度1 低风险自动发布」置 `status="active"`；入库可逆（按 trace 回滚即移除）。
- 新增 `src/core/skills/sop.py`：`SopWriter` DI 接缝（`build_sop_prompt` + `sop_writer_with`，
  **skills 不 import LLM 抽象**，照 `memory/summarize.py` 先例）+ `SopExtractor`（归组 / 累积 /
  提炼 / 入库）。
- `DefaultLoop` 增收尾钩子：任务**成功**收尾时把「任务文本 + 行动/结果序列」交给注入的回调
  （`loop` 不 import `skills`——架构红线 `test_architecture`），`build_runtime` 注入
  `SopExtractor.observe`。**不新增触发面、不改终止语义**。

## Non-goals

- **语义归组**：归组仍是词法（命中已有技能的 `task_types`，否则任务词元签名）；语义匹配归 #7。
- **技能迭代 / A-B 定夺**：本次只做「首版提炼入库」，重复偏差触发 version 升级归 #8。
- **judgment 质量门**：不给提炼产物做质量打分（judgment 无生成原语；低质量 SOP 由 `status`
  与后续迭代兜底），记入 ADR-0048 已知缺口。
- **技能库持久化**：`SkillLibrary` 仍是进程内注册表（重启即失）——先于本变更存在的缺口。
- **失败轨迹的教训沉淀**：失败轨迹**不计入**累积（不是 SOP）；教训沉淀已有 memory/evolution 通道。

## Impact

- 规格：`skills/spec.md`（+1 Requirement）。
- 代码：新增 `src/core/skills/sop.py`；`src/core/skills/__init__.py` 导出；
  `src/core/loop/default.py`（收尾钩子）；`src/core/runtime.py`（构造 + 注入主/子 loop）。
- 契约：`doc/03-interfaces/skills-interface.md`（SOP 提炼一节）+ ADR-0048。
- 兼容性：未注入 writer 时 `SopExtractor` 不累积、不提炼（零 LLM 调用）；未注入钩子时 loop
  行为**完全不变**；`Skill` 模型、`SkillLibrary`、`SkillRouter` 签名均不动。

## Risks

- **误提炼（低质量 SOP 自动 active）**：只吸收**成功**轨迹且需同类任务累计 ≥3 次；
  `instructions` 为空则不入库；入库可逆（`Effect` 回滚即移除）。质量门留待 #8 迭代闭环。
- **词法归组漏并**：同义不同词的任务不会并入同组（各自成组、各自达阈值才提炼）——宁可分叉
  不误并；语义归组归 #7。
- **LLM 调用成本**：每组达阈值才提炼一次（阈值后清组），非每任务一调。
