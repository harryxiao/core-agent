# Phase 37：Procedural Memory（批次 `0196`~`0199`，4 change）

> **状态**：✅ **全闭**（2026-10-11；4 条 change 逐条独立收口：各自 change 目录 / ADR / 规格 delta
> （或规格中性）/ 四门禁 / 手工归档 / 单次提交）。
> **来源**：2026-10-11 用户提出「**Procedural 本质是基于长会话任务过程 — 提炼/验证/沉淀 — 的一套
> SKILL/SOP/工作流等技能资产，也是进化的一个概念，这个要需要有**」。逐行取证后确认这条线**只接了
> 上半场的一半**（见 §2 账目）。
> **为什么是一批而非一条**：采集面（`0197`，跨 `orchestration` ＋ `skills` ＋组合根）与发布面
> （`0198`，`skills` ＋ `judgment` 消费）是**两个独立缺陷**，改动面属不同 capability，且 `0196`
> 是为 `0197` 腾出安全位置的**前置硬化** ⇒ 沿 **Phase 34/35/36 先例**：**一个批次、多条 change**，
> 每条仍各自 change / ADR / delta / 四门禁 / 单提交。
>
> **红线（全批次）**：主方向封存 `exclude_source_prefixes=("beast.","pet")`（`runtime.py`
> **逐字不动**，phase-26）；密钥只引用不读取、**绝不**进日志/记忆（留痕**只报组键** / 会话键，
> **绝不回显正文**）；**维度1 技能库/SOP 全自动**（`phase-21.md:5`）—— 质量门必须是**自动判定**，
> **不得引入人工确认**；零三方依赖；`config*.yaml` / `.claude/settings*.json` / `uv.lock` 等**不提交**。

---

## §0 用户裁决的四个设计岔口（AskUserQuestion，2026-10-11）

| # | 岔口 | 裁决 |
|---|---|---|
| 1 | **提炼单位** | **orchestration 任务级**（复用现有 `DoneFn` 接缝 + checkpoint `state["trace_ids"]`）⇒ change `0197` |
| 2 | **验证方式** | **自动质量门**（judgment 判定，noul 原语）—— 守红线「技能库/SOP 全自动」⇒ change `0198` |
| 3 | **资产形态** | **SOP 文本**（沿用既有 `Skill.instructions`，**不**新增结构字段） |
| 4 | **批次范围** | **只做 G1（任务级过程提炼）+ G2（自动质量门）** |

---

## §1 批次总览（执行顺序 = 编号顺序）

| # | change（归档目录） | capability | 一句话 | ADR | 台账 | 测试基线 |
|---|---|---|---|---|---|---|
| 1 | `0196-orchestration-done-offload` | `orchestration` | 任务完成回调 `on_done` **卸载出事件循环**（`asyncio.to_thread`；先例 `0167`/ADR-0157）—— 为 `0197` 的模型调用腾出安全位置 | ADR-0186 | E133 | 2232 → 2234（+2） |
| 2 | `0197-task-level-sop-input` | `skills`＋组合根 | SOP 提炼新增**任务级过程**输入：`DoneFn` 处装配「目标 + 按 `plan.order` 聚合的子任务步序」→ **第二个** `SopExtractor`（异样本文件、`namespace="task"`） | ADR-0187 | E134 | 2234 → 2241（+7） |
| 3 | `0198-sop-quality-gate` | `skills`＋`judgment` 消费 | SOP **自动质量门**：注入判定接缝（noul），未过 ⇒ 不发布 + 清组 + 留痕（只报组键）；判定故障 ⇒ fail-open | ADR-0188 | E135 | 2241 → 2249（+8） |
| 4 | `0199-procedural-e2e-gates` | （架构测试，**规格中性**） | 端到端门禁：任务完成 → SOP 入库 / 拒绝门 ⇒ 不入库 / 过程取自记忆步序非 `reply`（`skip_specs`，**零 `src/` 改动**） | ADR-0189 | E136 | 2249 → 2253（+4） |

**批次合计**：测试基线 **2232 → 2253**（**+21**）；`openspec validate --all` **31 passed / 0 failed**；
四门禁（`ruff check` / `ruff format --check` / `pyright` **0-0-0** / `pytest -q`）**逐条全绿**。

---

## §2 账目（E133~E136，逐条根因 → 修法）

| 台账 | 根因（一句话） | 修法（一句话） | 归档 |
|---|---|---|---|
| **E133** | `TaskScheduler` 在 `astream` 协程内**同步**调用完成回调（`scheduler.py:290-292`）—— 当前无症状（只落一份廉价检查点），但 `0197` 要在其中跑**模型调用** ⇒ 一旦如此即**精确复现 E103/ADR-0157**（事件循环上的同步模型调用，阻塞流式产出、拖垮同波次并发，且被降级链静默吞掉） | `DONE` 分支改 `await asyncio.to_thread(self._on_done, …)`（**一处**调用点）；**不改** `_checkpoint`（判据是「是否承载模型调用」而非「是否同步」，P3 局部化）；时机 / 次数 / 顺序 / 终态**逐字不变** | `0196` / ADR-0186 |
| **E134** | SOP 只见**单轮**面（`_action_steps(ctx)`）—— 长会话任务**跨轮** ⇒ 每轮各自成样本、任务文本**逐轮不同** ⇒ `_group_key` 词元签名漂移 ⇒ 样本**永不归组**、累积**永不达阈**（`_SOP_MIN_SAMPLES=3`）⇒「长会话任务过程 → 技能资产」这条链**从未产出过任何东西**；且 `SubtaskOutcome.reply` 截断 2000 字**不足以承载步序** | 接入点**复用 `DoneFn`**（只在成功 `DONE` 调一次，与「只吸收成功」天然对齐）＋ 连接键 = `trace_ids` → `loop.steps.<tid>` ＋ 读取走 `_steps_lookup`（`MemoryBackend.search("")`，**零效应**不强化 `reuse_count`）＋ 纯函数 `compose_task_steps`（有上界，token 有界）＋ **第二个提取器实例**（异样本文件、`namespace="task"`：两路步序语义不同，混组即产出浑浊 SOP ⇒ 隔离是**正确性**要求） | `0197` / ADR-0187 |
| **E135** | 提炼拿到非空文本后**直接** `status="active"` 发布 —— **无任何质量判定**，且被拒**无留痕**；缺口早已明文登记（`skills-interface.md` §6「已知缺口：无 judgment 质量门」）；`0197` 接通任务级输入后样本文本更长、语义更不可控 ⇒ 风险抬升 | 门的形状 = **纯 callable** `SopGate`（skills 定契约 / judgment 供实现 / 组合根注入，守 ADR-0048）＋ 判定用 **noul** 原语（落 `judgment/skills.py`，镜像 `Guardrail`；**judgment 规格零改动**）＋ **两层 fail-open**（门守自身故障、`_gate_ok` 守契约边界 ⇒ 不得冒泡进编排收尾回路）＋ 未过 ⇒ **不发布 + 清组 + 留痕只报组键**（绝不回显正文）＋ **只挂任务级实例、仅在 JEV 配置时** ⇒ 缺省发布路径**逐字不变** | `0198` / ADR-0188 |
| **E136** | 「任务过程 → 技能资产」链三段**各自**只有单元锚（`0196` 线程 ident / `0197` 纯函数 `compose_task_steps` / `0198` `SopExtractor` 门分支）⇒「**真 `TaskScheduler` 跑完成功后，真组合根装配的提炼器真的把 SOP 入进真技能库**」**无端到端锚** | 新增 `tests/test_procedural_e2e.py` 四条端到端锚（真组合根 ＋ 真 `TaskScheduler` ＋ 真 `MemoryStore`；**只桩**模型接缝与子 Agent 执行单元）＋ **防空过断言** ＋ **反证**（逐条临时回退确认转红）；**零 `src/` 改动** | `0199` / ADR-0189 |

---

## §3 逐条收口（协议一致性）

每条**必走**：spec-first（或**规格中性**判定）→ ADR → 先红测试 → 实现 → 四门禁 → 手工归档
→ 台账 ＋ 记忆 → **单次提交**。**规格 delta** 落点：`0196`→`orchestration`；`0197`→`skills`；
`0198`→`skills`；`0199` **规格中性**（`.openspec.yaml` `skip_specs: true`，沿 `0156` / `0189` /
`0195` 先例 ⇒ 无 delta）。**judgment / orchestration（`0197`、`0198` 面）规格零改动**。

**归档方式**：`openspec archive` 在 symlink+WSL 下**必败** ⇒ 恒为**手工**（delta 合 canonical 时断言
**0 canonical Requirement-header 丢失 / 0 Scenario-title 丢失**，再移进 `doc/openspec/changes/archive/`；
规格中性者直接 `mv`）。归档断言：`0196` `orchestration` scen 49 → **50**（11 req 不变）；
`0197` `skills` scen 45 → **47**（10 req 不变）；`0198` `skills` scen 47 → **49**（10 req 不变）。

**能力面 canonical 变化**（`doc/openspec/specs/`）：`orchestration`（异步执行单元契约 + **收尾回路
不阻塞**）；`skills`（SOP 提炼 + **任务级过程输入** + **自动质量门**）。逐条 Scenario 计数见各自
change 的 delta 与 `doc/04-testing/test-cases.md` §109~§112。

**本批次的两条方法论教训（值得记）**：
1. **`0198` 的「实测订正」**：初版两条 fail-open 用例走「provider 抛错」⇒ **转红** —— `DecisionRouter`
   **不冒泡**异常而是**回退主 LLM**（桩回退返回空串 ⇒ `_parse_yes("")` = `False` ⇒ 门**拒**）。
   ⇒ 用例改桩**路由层**并把该边界写入 ADR 决策③。**若不做该用例，此误解不会被发现**。
2. **`0199` 的「桩漂移两坑」**：ⓐ 状态机身份是 `task_id`（复用已 `DONE` 的 id 抛
   `INVALID_TRANSITION: done → verifying`）⇒ 每次 `run` 用新 id（归组键取自**目标**，与 id 无关）；
   ⓑ 桩 `LoopPlugin` 需按**目标文本**映射 trace_id 才能对上 `loop.steps.<trace_id>` 条目。

---

## §4 遗留与显式不做

- **本批次外（用户裁决）**：
  - **G3 工作流结构化资产**（`Skill` 新增 steps 结构）—— 用户裁决「**SOP 文本**」；
  - **G4 技能→插件结晶接线**（wire `SkillCrystallizer` ＋ 修 `evolution._crystallize_skill` 产出的
    **无 `instructions` 空壳技能**）；
  - **G5 L3 记忆层 ↔ `SkillLibrary` 两面统一**（memory spec 现无「结晶/光谱」条款）；
  - **改写 / 重排现有** per-turn SOP 采集路径（本批只**新增**任务级入口）。
- **本批次新增的已知局限**：逐条登记在 `coding-plan/known-risk.md` **§3**（按 ADR 归类
  ADR-0186~0189）—— 例如 `0196` 不卸载 `_checkpoint`、`0197` **续跑已 `DONE` 任务会二次触发**
  （跨进程无去重面）且纯回答子任务在聚合中缺席、`0198` **拒即丢批**且只挂任务级实例、
  `0199` 桩子 Agent 不真跑循环（不验 `loop.steps` 写入侧）。
- **`0199` 后仍开账**：**E27**（IM 网关未接线）/ **E55** / **C7**（TTS）/ **E91** / **E100**（余运维
  动词）/ **E101**（hooks 实现）—— **未闭**，仍登记于 `coding-plan/known-risk.md` §1。
  **账外**：`_action_steps` 的脱敏不对称（未开 change）。

---

## §5 关联

- 前置：`coding-plan/phase-36.md`（长任务硬化，6 change `0190`~`0195`）·
  `coding-plan/known-risk.md`（§1 账目 E133~E136 已闭、§3 已知局限）。
- 逐条细节：`doc/openspec/changes/archive/2026-10-11-0196-orchestration-done-offload/` …
  `…-0199-procedural-e2e-gates/`（各有 `proposal.md` / `tasks.md` / `design.md`；`0196`~`0198`
  另有 `specs/`；`0199` 另有 `.openspec.yaml`）；用例与红态证据：`doc/04-testing/test-cases.md` §109~§112。
- 测试锚点：`tests/test_orchestration.py` / `test_skills.py` / `test_task_sop.py` /
  `test_judgment.py` / `test_procedural_e2e.py`。
