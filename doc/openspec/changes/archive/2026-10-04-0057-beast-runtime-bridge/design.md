# 设计：beast-runtime-bridge

## 决策 1：作用域强制下沉到路由期（而非调用方自觉）

R5 原文把专属路由交给「BeastSession 按 agent_id 前缀过滤候选」——但 `BeastSession` **不持有
路由**（路由在组合根闭包里）。候选池又来自全局库，故「谁来过滤」这个位置上**没有主体**。

否决：
- **A. 在 `BeastManager` 里过滤**：manager 拿不到 `SkillRouter` 的候选（hints 闭包在 runtime）。
  要么把路由面暴露给 beast 层（新增跨层依赖），要么重造一份路由（第二真源）。
- **B. 只注册、不做域过滤**：主 Agent 会把 `beast.*` 神通路由进 prompt——**直接违反 R5**，且在
  主循环 prompt 里灌入 20 条无意义技能，与「token 有界」冲突。

选定 **C. 路由期带 `domain` 参数过滤候选**：`SkillRouter` 本来就拥有候选池，加一个可选作用域参数
是最小且唯一有主体的位置；`domain=None`（主 Agent / 通用子 Agent）语义 = 只看通用技能，
**为既有调用方零行为变更**（现网无专属技能，候选集不变）。

## 决策 2：口径用「skill_id 形状」判定专属，不用命名空间注册表

判据：`skill_id.split(".")` 为三节且首节 `beast` → 专属，归属域 `beast.<次节>`。

- 与 `Beast.agent_id = "beast.<拼音>"` / `innate_skill = "beast.<拼音>.<技能>"` 天然对齐，
  `match(task, domain=beast.agent_id)` 即可。
- 不引入「专属注册表」这种新状态（会与技能库落盘产生第二真源）；形状即约定，写在规格里。

## 决策 3：loop_factory 注入而非「一兽一 loop 预建」

`build_runtime` 里预建 20 个 loop = 20 份 planner/assembler/hooks 常驻，全无用（同一时刻在岗兽
屈指可数）。改为 `loop_factory(beast)` 惰性装配，`BeastManager.summon` 按需造；**每次 summon
造新 loop**（召回后重召 = 新会话，语义干净；loop 无跨会话需保留的状态——记忆在共享 `MemoryStore`）。

配 `router=MultiAgentRouter([])`：专用实例，避免把神兽画像与 coding/research 子 Agent 混进同
一个路由器（`agent_router` 的 fallback 语义对神兽无意义）。`handoff` 走显式 target，不需 fallback。

## 决策 4：`_loop_hooks(domain)` 参数化，主/子/兽三处共用

`_loop_hooks` 已是「每 loop 一组钩子闭包」的工厂；加 `domain=None` 参数后：
主 loop 与 coding/research/general 子 Agent 传缺省（无专属技能可见），`_beast_loop(beast)` 传
`beast.agent_id`。**共享同一 `skill_feedback`/`sop_extractor`/`skill_iterator`** —— 神通命中/成败
与通用技能同一套反馈与迭代链路（神通的进化与普通技能同构，不搞第二套）。

## 决策 5：`entry` 走 `build_runtime`，与 `_pet` 同口径

`summon`/`recall` 此前造裸 `BeastActivator()`——那是「每次新起空装配」，与 `_pet` 的
`build_runtime(ConfigManager(...))` 口径不一致。改为同一装法（含 try/except → stderr + 退出码 1）。

## 风险与接受项

- **召唤即真跑 loop**：CLI `summon` 现在会真调 LLM（此前是 echo）。这是 R4 的**本意**（独立 loop
  真实执行），非回归。无 LLM 可达时 planner 降级为「LLM 调用失败」回复，不抛裸异常（既有保障）。
- **神通注册落盘**：`register_innate_skills` 写进带路径的 `SkillLibrary`（0050 口径）。重启后重复注册
  为幂等覆盖（`skill_id` 为键），不产生重复条目。
- **本变更不接线**：神兽的多兽**并行调度**（`TaskScheduler` 与神兽的配合）、神兽专用的权限策略、
  `/summon` 斜杠与 WebUI 自然语言入口的**真实 UI 接线**（`BeastActivator` 三入口契约已备，UI 侧
  仍由既有接入层驱动）——均不在 E3 范围。
