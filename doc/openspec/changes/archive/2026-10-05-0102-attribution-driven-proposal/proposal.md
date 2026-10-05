# 提案 — 归因驱动提案与结晶语义诚实化（change 0102）

## Why

`coding-plan/phase-21.md` §1 列的**五处断裂**中，change `0101` 已闭合断裂 0/1（trace 通路 +
模块归因）。本 change 收尾**余下两处**——二者同为「数据到了、但语义被写死或谎报」：

1. **断裂 3 — 提案的 `kind` 静态绑定**：`Proposer.__init__(*, kind: Literal["skill","plugin"] = "skill")`
   （`proposer.py:21`）在**构造期**把 kind 钉死为缺省 `"skill"`，而 `risk_level` 又由它派生
   （`proposer.py:35`：`"high" if self._kind == "plugin" else "low"`）。组合根 `runtime.py:450` 取
   `Proposer()` 无参 ⇒ 生产**每一个**候选的 `kind` 都是 `"skill"`、`risk_level` 恒为 `"low"`。
   ⇒ change `0101` 刚打通的**模块归因证据**（`plugin_id="loop.default"`）虽然能被 `Diagnoser`
   归因，产出的候选却仍是「技能库级」——**架构级缺陷被降格为技能级提案**，§5.2 的归因成果在
   提案阶段被抹掉。**账本原判（phase-21 §1 断裂 3）经一手核实为真**：`kind` 与归因对象无关。
2. **断裂 4 — 结晶结局谎报 `published`**：`EvolutionEngine._crystallize_plugin`（`engine.py:259-271`）
   对 `kind="plugin"` 的候选只做一件事——把候选的 `delta["issue"]` 写进 **L3 记忆**
   （经可选 `memory_crystallizer`），随后 `return EvolutionOutcome(status="published", …)`。
   **没有任何架构产物被发布**（本仓无「架构补丁应用器」，也没有可晋升的世代 —— 见 E31），
   `published` 对外是**谎报**；CLI 还会照此打印「已确认并发布：published」（`entry.py:1022`）。

**关键裁决（承接 change `0101` 的 (b) 口径）**：架构级候选的确认链路**保持**「人工批准」语义，
但**结局词表诚实化** —— 批准并过门后登记为 **`accepted`**（「已批准、待人工实施」），
`published` 只留给**真的**落了产物的技能分支（`_crystallize_skill` 确实 `SkillLibrary.register`）。
这与 (b) 的「登记批准 + **不谎报 published** + 开观察期」逐字一致。

## What Changes

- **新增单一真源常量 `INTERNAL_PLUGIN_IDS`**（新文件 `src/core/evolution/plugin_ids.py`）——
  13 个内部核心模块 id 的 `frozenset`，作**归因白名单**（文档串写明：非 `PluginRegistry` 成员）。
- **`Proposer` 的 `kind` 由归因驱动**（`proposer.py`）——
  构造参数降级为**显式覆盖**：`kind: Literal["skill","plugin"] | None = None`；缺省 `None` 时
  `propose()` 按 `diagnosis.target_plugin in INTERNAL_PLUGIN_IDS` 判定（命中 ⇒ `plugin`/`high`，
  否则 ⇒ `skill`/`low`）。**显式传入仍覆盖归因** ⇒ 既有 `Proposer(kind=…)` 调用与测试逐字不变。
- **架构级结晶结局改为 `accepted`**（`engine.py`）——
  `_crystallize_plugin` 返回 `EvolutionOutcome(status="accepted", …)`；L3 记忆留痕与
  `crystallize` 的观察期开窗（`engine.py:178`）**保留**。技能分支**保持 `published`**。
- **结局词表登记**（`models.py` `EvolutionOutcome.status` 注释）+ **CLI 文案订正**
  （`entry.py:1022` 的「已确认并发布」在架构级分支改为「已批准（待人工实施）」口径）。

## Non-goals

- **不新建 `PluginRegistry` 载体、不做架构代码自动应用**（承接 (b) 口径，见 change `0101` design §1；
  相关欠账已登记为账本 **E31**）。
- **不改 `run_cycle` / `maybe_run` 的默认结局**：全链路缺省仍是 `pending`（人工门语义一字不动）。
- **不改工具通道归因、不改 `Diagnoser` 归因、不改 auto-dissolve**（phase-21 §6 明文「本 Phase 不改」）。
- **不做工具级 trace 通道**（`action_completed` 未 `_trace` ⇒ evolution **skill 分支在产线仍无输入**）
  —— 已登记为账本 **E30**。

## 风险

| 风险 | 处置 |
|---|---|
| 归因驱动的 `kind` 让低风险候选变高风险，**人工门变严** | 这是**修 bug 的目标行为**（架构级缺陷本就该走架构级门）；且 `risk_level` 只影响**审批单要求**，不影响是否放行 |
| 既有测试断言 `Proposer()` 的缺省 `kind == "skill"` | 已核：既有用例的 `target_plugin` 全是 `memory.retrieve` / `tools.*` 等**非**白名单 id ⇒ 归因分支仍得 `skill`/`low`，逐字不变 |
| `accepted` 是新结局词，消费方遗漏 | 已核全仓 `published` 消费点仅 `entry.py:1022` 一处文案 + 测试；`EvolutionOutcome` 是数据载体，无状态机依赖 |
| 结局改名被读作「放宽人工门」 | 明确相反：`accepted` 是**比 `published` 更弱**的断言（批准 ≠ 发布），人工门不放宽 |
