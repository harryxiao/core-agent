# Proposal 0205 — SOP 技能退役（连续退化自动退役 + 粘性防复活，缺省关）

## 为什么

「四类记忆 / 程序化记忆是否闭环」取证确认：**程序记忆缺溶解**。四处证据：

- **取值域已有、生产无路**：`Skill.status` 的取值域含 `"deprecated"`（`models.py:26`），但
  `src/` 内**无任何生产路径**会置它。
- **迭代退化只丢草稿**：`SkillIterator.decide()`（`iteration.py:135`）在 A/B 退化时只
  `del drafts[draft]`，注释明写「退化：只丢草稿，技能本体不动（**不置 deprecated**）」。
- **evolution 溶解 id 前缀硬编码**：`EvolutionEngine.dissolve` 的 `skills.evolution.` 前缀
  （`engine.py:227`）**永不命中** `skills.sop.<hash>`；唯一 id-agnostic 的
  `SkillCrystallizer.dissolve` 是**死代码**（`src/` 内零构造）。
- **规格写死了单次禁令**：`doc/openspec/specs/skills/spec.md:303-305` 的「技能迭代闭环」定夺
  bullet 明文「败者…技能 SHALL NOT 被置 `status="deprecated"`」，且 Scenario `A/B 退化丢弃新版本`
  （`:323-326`）断言其不变。

后果：SOP 技能一经自动 `active`（`sop.py:127`，维度1「低风险自动发布」）即**永久可路由**——
与 P2「一切副作用可逆」及「失败即沿反方向溶解」的隐喻相悖；一条持续退化的 SOP 无路退出。

## 做什么

**只做一件事**：给 SOP 技能一条**自动、可逆、缺省关**的退役路径。

- `SkillLibrary.deprecate(skill_id, *, effect_tracker=None)` —— **逐字镜像既有 `activate`**
  （改状态 + 落盘 + 登记可逆效应 `skills.deprecate`，undo 复用既有 `_restore_status`）。
- `SkillIterator` 在 A/B **连续**退化达阈（`RETIRE_AFTER_DEGRADATIONS`，缺省 3）时自动
  `deprecate`；一次提升**归零**计数。
- **粘性防复活**：已退役的 `skills.sop.<hash>` 在**同组键重抽**时 SHALL NOT 被无声复活为
  `active`（`sop.py::observe` 守卫：跳过 `register` + 清组 + 只报组键）。
- 用户裁决（③）：**自动**判定，SHALL NOT 依赖人工确认（守红线「维度1 技能库/SOP 全自动」）。
- 用户裁决（④）：**缺省关、显式开启**（`skills.retirement`，全仓首个 `skills.*` 配置键）。
- 用户裁决（⑤）：退役**粘性**，复活仅经**显式** `SkillLibrary.activate`（既有面，本 change 不动）。

## 关键决策：为什么是「退化计数」而不是「新开判据」

A/B 定夺**已经**算出「新版本更差」这个信号（`result.winner != draft`）——缺的只是**把它累计
起来**。同一信号单次出现是方差、连续 N 次出现才是趋势 ⇒ 复用 `decide()` 既有分支（`result.winner`
与 `draft` 本就在局部），**不新开评分逻辑、不新开判据面、不新开会话面**。改动面 = 一个计数器 +
一处阈值分支。

**为什么不走 evolution 溶解**：ADR-0011 把「溶解」划归 evolution；ADR-0052 已为 evolution
结晶插件补齐「观察期回归自动溶解」，但那条路依赖**留出集基准**，而生产 `Evaluator` 无基准 ⇒
`freeze`（`runtime.py:793-796`）⇒ 对 SOP **结构性不可达**。本 change 的退役是 **`skills`
自有的、反馈驱动（迭代退化）的、限定于 `skills.sop.*`** 的生命周期动作——与 evolution 的
「留出集回归」**判据不同（绝对分差 vs 连续退化）、对象不同（结晶插件 vs SOP 技能）、数据源不同
（留出集 vs 执行成功率）**，**不重叠**。ADR-0195 明写此边界。

## 规格影响

`skills` **MODIFIED** 一条要求「技能迭代闭环（skill iteration）」—— 把 `status="deprecated"`
的**绝对禁令收窄为单次**并前向引用新要求；同块内 **MODIFIED** 一条 Scenario `A/B 退化丢弃新版本`
（标题不动、GIVEN 收窄为「**单次**退化」、THEN 逐字保留）。**ADD** 一条要求「SOP 技能退役
（skill retirement）」，含 6 Scenario。canonical Requirement **10 → 11**，Scenario
**49 → 55（+6）**。其余 9 条 Requirement **逐字保留**。

## 风险

- **误退役**：开关缺省关 ⇒ 默认零风险。开启后仍须**连续 3 次** A/B 退化（单次方差不足以触发）；
  一次提升即归零。
- **退役是「退出路由」不是「删除」**：技能仍在库中（`status="deprecated"`），路由候选放行集只含
  `active`/`gray`（`router.py:98`）⇒ 自动退出注入面；可回滚、可显式 `activate` 复活。
- **MODIFIED 是本仓最高风险的规格编辑类型**：只能靠 `openspec validate` + 手工归档断言
  （0 Requirement-header 丢失 / 0 Scenario-title 丢失）兜底。
- **粘性防复活只覆盖 SOP 正路**：既有旁路（`VersionManager._deprecate` / `SkillCrystallizer.dissolve`
  / `EvolutionEngine.dissolve`）各自置状态却不共享本次 trace——本 change **不动**，登记为已知。
