# Phase 18 — 长期记忆固化自动化 + 技能进化双维度（SOP 技能库全自动进化 + 架构级进化人工审核）

> 里程碑：**M4 自进化收口**。记忆从 Phase 17「语义落盘」升级为「固化式长期记忆」；技能进化按风险域拆成**两个维度**——维度1「技能库/SOP 进化」全自动无人值守（日常任务→SOP→Skill→持续迭代，仅技能库层、不动架构代码），维度2「架构级进化引擎」保留人工审核（涉及架构代码，HITL `confirm` 必审）。
> 位置：横切 `memory`（protocol/store + 新增 consolidation/forgetting）× `skills`（新增 SOP 提取器 + 语义路由 + Skill 迭代）× `evolution`（confirm 收口 + auto-dissolve）× `judgment`（JEV 优先、LLM 兜底的决策基础，已内建）。
> 上游：Phase 1（memory）、Phase 5（evolution 四阶段）、Phase 11（judgment/JEV）、Phase 15（Validator/Evaluator/SandboxManager/HITL）、Phase 17（语义记忆落盘 + session 维度）；本 Phase 不新增 capability 三方依赖。

---

## 0. 核心结论（先回答「能否全部自动化」）

| 环节 | 能否全自动 | 结论 |
|---|---|---|
| 记忆 写入 / 检索 / 压缩 / 固化 / 遗忘 | **能，100% 全自动** | 记忆操作可逆（`Effect` undo 已内建）、无副作用，放权安全 |
| 维度1 技能库/SOP 进化（任务→SOP→Skill→迭代） | **能，100% 全自动** | 仅动技能库层（L3 Skill 封装 + instructions=SOP 载体），不触碰架构代码，无架构级副作用 |
| 维度2 架构级进化（L4 对架构代码升级） | **人工审核（HITL）** | 涉及架构代码，`confirm` 必审，不因低风险自动放行 |
| 进化 回滚（dissolve） | **能，全自动** | 观察期回归指标超阈值自动降级，保留教训（两维度均适用） |
| JEV 决策 | **JEV 优先、LLM 兜底** | 无 JEV / 不可达 / 超时 / 低置信度自动 `fallback` 主 LLM（传统方式），已实现 |

**一句话结论**：记忆全自动；技能进化分两层——**技能库/SOP 层全自动无人值守**（省 token 的核心收益来自这里），**架构代码层保留人工闸门**；决策统一 JEV 优先、LLM 兜底，二者缺一不可。

---

## 1. 范围与定位

### 1.1 现状（已实证）

- **Memory**：冷热区（`_hot` dict + `FileBackend`）；`read` 单因子 `relevance` 排序 + `_truncate` budget 截断（store.py:56-68 / 122-131）；`compact` 仅是 JEV 小模型「保留/丢弃」评分，**无摘要式压缩**（store.py:110-118）；`session_id` 已支持（protocol.py:32）。
- **维度1 技能库（skills）**：`Skill` 已含 `instructions` 字段（SOP 载体雏形，models.py:15-26）+ `version` + `status`；`SkillLibrary` 静态注册 + schema 校验 + 前置条件检查（library.py:23-65）；但 `SkillRouter._score` 是**词法命中** `hits/len(terms)`（router.py:41-46），非语义匹配；`SkillCrystallizer` 只做 L3→L1 结晶判定与溶解（crystallizer.py:40-60），**无「任务轨迹→SOP→Skill」提取能力**；**无「重复任务发现 skill 不完善→持续迭代」闭环**。
- **维度2 进化引擎（evolution）**：四阶段闭环 diagnose→propose→validate→evaluate；`Proposer.propose` 产出 `GenerationCandidate`（`kind="skill"/"plugin"`、`status="pending"`），**不自动发布**（proposer.py:25-34）；候选需 `confirm()` 才 `crystallize()`（engine.py:34-177）；`Collector` 从行动→结果对采集经验（collector.py:20-29）。**已满足「架构级人工审核」要求**。
- **JEV**：`DecisionRouter.decide` 对 provider 不可达 / 超时 / 低置信度自动 `fallback` 主 LLM（judgment/router.py），**fallback LLM 决策已实现**。

### 1.2 业内主流做法（对齐基线）

| 范式 | 来源 | 与本 Phase 的映射 |
|---|---|---|
| 分层内存 + 内存页调度 + 自编辑记忆 | MemGPT/Letta | `read` 预算管理已是雏形；缺「自主整合/改写」 |
| Memory Stream + 检索三因子（recency×importance×relevance）+ Reflection 反思树 | Generative Agents (斯坦福 2023) | 检索多因子化 + 摘要式固化（consolidation） |
| 技能库 + 自动课程 + 沙盒验证 + 失败反思重试 + 自动回滚 | Voyager (NVIDIA 2023) | **维度1**：技能库已有雏形，缺「任务→技能」自动提取（SOP 提取）+ 自动迭代 |
| 候选→验证→发布 + canary/灰度 + 自动回滚 | AutoGPT / self-evolving | **维度2**：已有 Validator/Evaluator/SandboxManager（P15），缺发布决策门与自动回滚收口 |
| 长期记忆 = 检索 + 摘要 + 遗忘 三件套 | Letta 等 | 摘要压缩（替代「保留/丢弃」）+ 遗忘衰减 |

### 1.3 差距清单（本 Phase 交付物）

**A. 长期记忆全自动化（4 项）**
1. `MemoryEntry` 增 `importance` / `kind`（episodic/semantic）字段（向后兼容）。
2. `read` 检索多因子化：`score = relevance × recency_decay × (1 + log(1 + reuse_count)) × importance`。
3. 摘要式压缩：`compact` 从「保留/丢弃」升级为「合并同类 + 提炼摘要」，产出 semantic 条目（保留 source trace_id 引用，可逆）。
4. 固化（consolidation）+ 遗忘（forgetting）：episodic → semantic 提炼；低分条目衰减归档（不物理删除，可 `audit`）。

**B. 维度1 技能库/SOP 进化（3 项，全自动，不动架构代码）**
5. **SOP 提取器（SopExtractor）**：从同一类任务的轨迹（行动→结果对 + 会话历史）提取标准作业流程，提炼为 `Skill`（`instructions`=SOP 步骤、`task_types`=任务归组）；LLM 提炼走 judgment（JEV 提炼不足则 fallback LLM）；提取结果经 `SkillLibrary.register()` 入库（复用现有 schema 校验）。这是「下次类似任务直接参考 skill 省 token」的核心来源。
6. **语义路由**：`SkillRouter` 评分从词法命中 `hits/len(terms)` 升级为语义匹配（JEV 语义打分、fallback LLM），词法保留为 fast path；使「类似任务」能命中对应 Skill。
7. **Skill 迭代闭环**：执行 skill 时记录「命中 + 结果反馈」，重复任务发现 skill 不完善（执行偏离 / 结果不达标）→ 触发迭代（`version` 升级 + `ABResult` 对比，复用 models.py:29-35）；迭代后仍走低风险自动发布。

**C. 维度2 架构级进化（收口 + 决策基础，人工审核）**
8. **confirm 必审收口**：架构级候选（`kind="plugin"` 或涉及架构代码的 delta）一律走 HITL `confirm`，**不引入「低风险自动结晶」**；`risk_level` 标注仅用于区分「维度1 技能库（可自动）vs 维度2 架构（必审）」。
9. **auto-dissolve 自动回滚**：结晶后登记观察期，evaluator 持续采样回归指标，超阈值自动 `dissolve`（降级为 L3 技能 + 保留教训），两维度通用。
10. **JEV fallback 声明**：决策统一走 judgment——JEV 优先、无 JEV/不可达/超时/低置信度自动 fallback 主 LLM（已实现，本 Phase 仅收口声明，不新增代码）。

**D.（P2 可选，本 Phase 不实现）** 自动课程（Voyager 式自主目标生成），为「自动迭代内部其余模块」铺路。

**E. 遗留任务（来自 Phase 17.5 §3.1 走查 + 2026-10-04 复核修正）**

> 2026-10-04 复核结论：以下为 Phase 17.5（接线补丁）实施后仍存留的架构级欠账。
> 复核发现一个**被遗漏的前置（P0）**，且原「C7→B4→B5→B6」顺序**不成立**——已按真实
> 依赖重排（见 §5-11）。**P0 完成前，B4/B5/B6 及 B2 的语义在生产均不可见。**

- **P0（前置，最关键）装配器整条路径在生产是死路径** ✅ **已完成**（2026-10-04）：`build_runtime` 现构造 `CoreProfileEngine`（load_global + load_project + assemble）并把装配器接入主/子 planner；宪法 → `constitution:v1` coeffect、项目信息 → 装配包 `facts`。冒烟验证：真实 `<repo>/Core.md` 的 7 行项目信息已注入。B2/B5/B6 随之在生产生效。：`build_runtime` 两处调用
  （`entry.py:281`、`:688`）均**未传 `assembler=`** → 生产侧 `planner._assembler is None`
  （`runtime.py:191/231` 仅把 None 透传）→ **L2 事实注入从不发生**。且宪法/项目信息素材的
  加载器 `GlobalProfileLoader`/`ProjectProfileLoader`（`core_profile/loader.py`）
  **无任何生产调用方**。即 Phase 17.5 §3.1 只改了装配器内部（query 修正），**没把它接上
  runtime**——B2 目前在生产不可见。落点＝`build_runtime` 构造 `DynamicAssembler(memory=memory,
  constitution=..., project_info=...)` 并传入主/子 planner，接入 profile loader 取素材。
  spec 已有「宪法约束注入」「项目信息注入」两条 Requirement 兜底（属**补齐已声明未实现项**，
  非新需求）。**B5/B6 亦依赖此项才生效。**
- **C7 embedder 接入（非机械接线，须先决策）**：`runtime.py` 构造 `MemoryStore` 未传 embedder
  → 运行时恒走词法 `_lexical_sim`，「语义检索」名存实亡。但：
  ① **契约不匹配**——`MemoryStore.embedder` 是**批量可调用** `(list[str]) -> list[list[float]]`
  （`store.py:38`、`relevance.py:62`），rag 的 `Embedder.embed(text) -> list[float]`
  （`embedder.py:38`）是**单条** → 需适配器；
  ② **成本**——`relevance._similarity` 每次 read 对**每个候选**调 embedder → **N+1 次
  embedding/read**，须定策略（写时缓存向量 or 离线 `HashEmbedder`）→ **先落决策（建议 ADR）**；
  ③ **强耦合**——与交付物 #1/#2（`importance`/`kind` + 多因子重排）是同一件事的两半，
  须一并落地避免返工。落点＝交付物 #1/#2 时一并接，带缓存策略；模型/密钥**只引用不读取**。
- **C8 写侧无 consolidation/forgetting**：`remember` 只增不整合、不衰减（已覆盖于交付物
  #4/#5，此处仅登记落点，不重复实现）。
- **B4 `ContextPack.skills` 恒空——判冗余，已删除**（2026-10-04，change
  `0044-semantic-skill-routing`）：技能**已经**进 prompt——planner 有 `skill_router` 回调
  （`runtime.py` → `planner._skill_hints` → 「可用技能」块），该字段**无生产者、无消费者**。
  用户定夺**删除该字段**（**不采纳**「装配器填充、planner 读 pack」：技能会与事实争同一预算，
  「先裁 facts、skills 吃剩余」在记忆丰富时把技能挤出 prompt，比今天的恒注入退化）。
  `pending` 不在范围（参与必保预算判定，非恒空字段）；**不单列为独立任务**。
- **B5 `_trim` 头部阻塞** ✅ **已完成**（2026-10-04）：原 `_trim` 遇首个放不下的项即
  `break` → 单项超预算会**连带掐断其后所有更小的低相关项**（头部饥饿）；且
  `pack.skills = self._trim(pack.skills, 0)` 使 **skills 恒空**。修正：`break` → `continue`
  （跳过放不下的项，保留其后可容纳项）+ skills 改用「事实裁剪后的**剩余预算**」。
  **排序职责仍归上游**（`pack.facts` = 项目信息 + `memory.read` 的 `rank` 降序结果），
  `budget.py` 只持有无分数的 dict，故不做重排——原落点写的「按得分排序后截断」改为
  「保序 + 跳过」，更小且不重复承担排序。纯实现修正，规格无涉（spec 只要求「超预算裁剪
  低相关度内容」）。测试 `tests/test_context.py` +2（跳过大项保小项 / skills 用余量）。
- **B6 仅 reason 阶段装配 —— 前提不成立，判为「按架构如此」（关闭）**：`assembler.build`
  唯一调用点＝planner `reason`（`planner.py:124`），这是**数据流的必然**而非缺口——
  `用户输入 ─► Loop.perceive ─► ContextEngine.assemble(+retrieve 注入) ─► LLM(Reason)
  ─► PermissionGuard ─► Loop.act ─► ToolProvider.invoke ─► Loop.remember`：装配是 **Reason
  前的一次性步骤**，`perceive` 在其**上游**（B2 已明确把检索移出 perceive），`act`
  消费的是 Reason 已决策的动作（工具选择发生在 Reason，tool schema 在彼处注入）。
  context spec 亦无 perceive/act 阶段装配的 Requirement（`stage` 定位为「装配阶段标注、
  暂不参与事实选择」）。**结论：不实现**；唯一残留（`stage` 语义化/阶段化权重）并入
  **A3**（已登记为可选），不独立排期。
- **P0b 人格 → L0 记忆层** ✅ **已完成**（2026-10-04）：`build_runtime` 在装配画像后，将
  人格分区以稳定 id `core-profile:personality` **幂等**写入 L0（`source=core-profile`）；
  测试锁定幂等（两次装配同 id 不重复）。L0 优先级最高，读时随候选带出、受预算截断约束。
- **A1 `LoopContext.memory` 遗留字段** ✅ **已完成**（2026-10-04，commit db204dc）：全仓确认
  无消费方后删除字段，同步 `loop-interface.md`（连带清除文档里的幽灵类型 `MemoryPack`）。
- **A3 `stage` 装饰性参数** ✅ **已完成**（随 B2 / change 0038）：`context-interface.md` 与
  `context/spec.md` 已如实标注 stage「暂不参与事实选择」。仍可选：赋予阶段化权重（留待按需）。

---

## 2. 里程碑验收

> **进度快照（2026-10-04，更新）**：遗留收口序 ①②③④ 已完成——A1/A3 清账（`db204dc`）、
> P0 装配器接线（`a35fbbf`）、P0b 人格→L0（`2f58ab1`）、**#1/#2 + C7**（`13c00e7`）、
> **B5 预算裁剪修正**（`8a1f531`），**B2 语义与语义检索均已在生产生效**。
> 交付物 **#1/#2 + C7** 已按架构最优拆分落地并归档：`0039-memory-multifactor-recall`
> （纯 memory：`MemoryEntry` 增 `importance`/`kind`、`read` 多因子重排
> `relevance×recency×(1+log1p(reuse))×(1+importance)`、`memory/embedding.py` 单条→批量适配器、
> 文本哈希向量缓存、`build_runtime` 的 `embedder` DI 参数）→ `0040-memory-embedding-config`
> （`llm.embedding_model` 配置旋钮 + 以该模型**另构造** provider → `LLMEmbedder` → 注入；
> 未设置/不可达回退词法，不阻断启动）。ADR-0045 已转 **Accepted**。
> `importance` **自动打分**留至 #4/#5（接 judgment `score`），本批仅加字段 + 参与排序。
> **B6 判为「按架构如此」关闭**（装配是 Reason 前一次性步骤），B4 判冗余待并入 #7。
> 
> **#3 摘要式压缩 已完成并归档**（2026-10-04，change `0041-memory-summary-compaction`，
> 608 tests 绿、ADR-0046 Accepted）：memory 新增 `Summarizer` DI 接缝（`memory/summarize.py`：
> `build_prompt` + `summarize_with`，**memory 不 import LLM 抽象**，照 `batch_embed` 先例）；
> `compact` 注入摘要器时按 `session_id` 聚合 L2 episodic → 一条 `kind="semantic"` 摘要条目
> （`id=compaction.summary.<sid>`、`source="compaction"`、`trace_id=compaction.<sid>`、
> `tags` 带 `from:<原 id>` 出处）→ 原条目 `migrate` 到 L4 归档（不删除），**整批按同一 trace 可
> 撤销**。一并修 `migrate` 不记 `EffectTracker` 的不可逆缺口。`context.Compactor.persist` 收口为
> `kind="semantic"` + 出处标签，并明确定位为**启发式降级路径**（LLM 提炼统一归 memory 通道）。
> **触发点已接活**：`DefaultLoop` 注入 `compactor`，每轮 `observe` 后按 `should_compact` 判定 →
> `persist` → `memory.compact`；终止语义不变（压实后仍按既有预算/轮数终止）。`runtime` 构造
> `context.Compactor(memory=memory)` + `summarize_with(主 LLM)` 并注入主/子 loop。
> **两处偏离原计划（已在 ADR-0046 记录）**：① 出处放 `tags`（`from:<id>`）而非 `source`——
> `source` 会作为出处标签进 prompt，塞 id 列表会污染 prompt 并白烧 token；② 压实效应按会话
> 共用 `trace_id`，`compact` 签名/返回值不变（phase-18 §6 要求）。
> **遗留**：生产侧 `session_id` 仍为空串（loop 不向记忆传会话标识）→ 实际按单一 `""` 组聚合；
> 会话维度生效需把 `session_id` 从 UI 会话透传到 `remember`（另立变更）。`UIAPILayer.compact`
> 仍是 no-op（ui spec 无该 Requirement，未擅自接线）。memory spec「并发压实一致性」仍无实现
> （单线程事件循环、无并发调用方，加锁属投机代码，另行登记）。
>
> **#4 固化 + #5 遗忘 已完成并归档**（2026-10-04，change `0042-memory-consolidation-forgetting`，
> 616 tests 绿、ADR-0047 Accepted）：**固化并入 `compact` 摘要通道**（不新增 `consolidate()`）——
> 注入 `compactor` 时**逐条目**调 judgment `score` 原语打分并写回 `importance`（逐条记
> `Effect(op="memory.importance")`，与压实同 trace `compaction.<sid>` → 回滚即恢复旧值）；
> 因 `score` 原语返回的是**条目集单一分数**，以 `_MAX_SCORED_PER_COMPACT = 20` 设调用上界。
> **价值门控**：会话内本轮取得分值的最高分 < `_CONSOLIDATE_THRESHOLD = 0.5` 即整体跳过（不提炼、
> 不归档、原条目留 L2 episodic）；**本轮没取得任何分值**（未注入 scorer / 打分失败 / 超出上界）
> 则**不设门槛**（宁可少提炼，不因决策服务抖动让记忆停止固化）。**打分失败 ≠ 打 0 分**（保持原值，
> 否则一次抖动清空全库重要度并误遗忘）。`compact` 里既有的**压实决策打分**改为失败降级
> `decision=None`（咨询性返回值、无副作用，不连带阻断固化）。
> **遗忘**：新增 `MemoryStore.forget(*, threshold=0.05) -> list[MemoryId]`，评分
> `recency_decay × (1 + log1p(reuse)) × (1 + importance)` 低于阈值（≈19 天零复用零重要度）的
> **L2 episodic** 条目 `migrate` 到 L4 归档（**不物理删除**、`audit` 可见、检索降权），逐条
> `trace_id=forgetting.<id>` 按 trace 可回滚；semantic / L0 / L3 不参与衰减。**触发并入 loop 既有
> 压实触发**：`persist → compact → forget`，三步各自降级（异常记 `maintenance_failed`），不新增
> 触发面、不改终止语义。
> **两处偏离原计划（已在 ADR-0047 记录）**：① 遗忘评分用 `(1 + importance)` 而非 phase-18 原文的
> `importance`——未打分条目（默认 0）会让评分恒为 0，首次遗忘即清空全库 L2 episodic；② 门控在
> 「本轮无分值」时不生效（原计划只写「达阈值才提炼」）。
> **遗留**：`forget` **无调度器**（只在 loop 压实触发时顺带执行，定时衰减循环需调度依赖，另立
> 变更）；`session_id` 仍为空串（同 0041）；无并发锁。
>
> **#6 SOP 提炼 已完成并归档**（2026-10-04，change `0043-sop-skill-extraction`，
> 616→626 tests 绿、ADR-0048 Accepted）：技能库**首次有了产出入口**——`src/core/skills/sop.py`
> 新增 `SopExtractor`：成功任务的「任务文本 + 行动/结果序列」按组累积，累计 `_SOP_MIN_SAMPLES = 3`
> 条即提炼一次，产物 `Skill(instructions=<提炼文本>, task_types=[组键], status="active")` 经
> `SkillLibrary.register()` 入库（可被 `SkillRouter` 命中），提炼后清空该组；入库登记
> `Effect(op="skills.register")`（`trace_id=skills.extract`）可按 trace 回滚移除。
> **归组**先词法命中已有技能的 `task_types`（复用其作组键，为 #8 迭代提供增量），未命中用任务词元
> 签名（`terms_of` 与 `SkillRouter` 同口径）。**接线**：loop 新增收尾钩子
> `SopObserver = Callable[[str, list[str]], object]`（**loop 不 import skills**——架构红线），
> 仅在**成功**收尾时提交（失败轮/超限终止轮不提交），钩子抛错记 `sop_extract_failed` 降级、
> 不改本轮结果与终止语义；`build_runtime` 构造 `SopExtractor`（writer = 主模型，经
> `sop_writer_with` 适配）注入主/子 loop。未注入 writer 时不累积、不提炼（零额外调用）。
> **一处偏离原计划（已在 ADR-0048 记录）**：计划写「LLM 提炼走 judgment」，但 judgment 只有
> choice / score / noul **决策**原语、**没有生成原语**——生成改走 DI 接缝（照 `memory/summarize.py`
> 先例），judgment 在技能链路上的角色留在 #7 语义路由打分。
> **遗留**：技能库仍是进程内注册表（无持久化，先于本变更存在）；样本仅进程内累积（不落盘）；
> 无 judgment 质量门（只吸收成功轨迹 + 阈值 + 可逆回滚兜底，质量门归 #8）；**B4（`ContextPack.skills`
> 恒空）本次未顺带填充**——`skills/spec.md` 与 context spec 均无「装配器填充技能字段」的 Requirement，
> 该字段的收口归 #7（语义路由一并处理）或判冗余删除。

> **#7 语义路由 已完成并归档**（2026-10-04，change `0044-semantic-skill-routing`，
> 626→637 tests 绿、ADR-0049 Accepted）：路由**词法 fast path + 语义兜底**——`SkillRouter` 增
> `scorer` 接缝（`SkillScorer = Callable[[str, list[dict]], dict[str, float]]`，候选以 dict 快照
> 传入）与 `threshold`；**仅词法全无命中**时才调打分器（避免把辅助决策成本抬到每个推理轮），
> 语义分 ≥ 0.5 才采纳并按分降序返回，**语义命中不再记 miss**（miss 是「无技能可用」信号）。
> 打分落 **judgment 域**（`judgment/skills.py::SkillMatcher`，照 `Compactor` 先例：**只吃 dict、
> 不 import skills**；skills 侧也不 import judgment）：`score` 原语只给「条目集单一分数」→ 逐候选
> 一次 `decide()`，坏答案/失败/回退（0.0）即略过。接线：`build_runtime` 仅在配置 JEV 时注入
> `SkillMatcher(router).score`（未配置 → 纯词法，零行为变化；JEV 不可达时回退分 0.0 自然退化）。
> **B4 收口（用户定夺）**：删除 `ContextPack.skills` 恒空字段 + `BudgetManager` 的裁剪/计量 +
> `context-interface.md` 字段与保留策略中 skills 一句 + `test_context` 对应用例（规格中性：context
> spec 从未提及 skills；构造方均未传该字段）。**遗留**：语义分只用于排序，**无历史成功率加权**
> （需命中/结果反馈闭环，归 #8）；候选未预筛（miss 时对全部 active/gray 技能逐条打分，K = 技能数）。

> **#8 技能迭代 已完成并归档**（2026-10-04，change `0045-skill-iteration`，637→649 tests 绿、
> ADR-0050 Accepted）：补上三处断链——① `instructions` **首次真正进 prompt**（组合根把命中快照
> `skill_hint`（id + 版本 + 步骤节选 ≤ 400 字符）交给 planner 渲染技能块，`SkillHint` 为纯 dict，
> loop 不 import skills）；② 命中/结果**按 `(skill_id, version)` 进程内累计**（`SkillFeedback` /
> `SkillStats`，`success_rate` 即 A/B 指标口径）；③ `VersionManager` 首获**生产调用者**
> （`SkillIterator`：`promote` 灰度 0.3 / `select` 选版 / `ab_test` 定夺）。触发门 = 样本 ≥ 3 且
> 失败率 ≥ 0.5 且已注入改写器（复用 `SopWriter` 接缝，skills 不 import LLM 抽象）；**退化只丢草稿**
> （草稿版本非库中 `Skill.version` → `_deprecate` 自然 no-op，技能不被误标 deprecated）；落地登记
> `Effect(op="skills.iterate")` 可逆。`loop` 收尾钩子由 `SopObserver(task, steps)`（成功专语义）扩为
> **`TurnObserver(task, steps, ok)`**（成功/失败都提交，`SopExtractor.observe` 仍只吸收成功），
> 事件更名 `turn_observer_failed`；两钩子**每 loop 一组闭包**（含子 Agent loop），状态不跨 loop 共享。
> **遗留**：改写 prompt 无失败轨迹（轨迹级诊断属 evolution 维度2）；样本进程内、跨进程归零；
> 无 cooldown；成功率只区分成败；**排序仍未接历史成功率加权**（数据源已具备）。

- **记忆**：跨 3 轮以上长对话后，`read` 命中率提升（同一事实不因截断丢失），semantic 条目可见且可追溯 source trace_id。
- **压缩**：注入 Compactor 后 `compact` 产出「摘要条目」而非「保留/丢弃布尔」，且摘要可逆。
- **维度1**：一条日常任务轨迹走完「任务→SOP 提取→Skill 入库→下次类似任务语义命中」全链路（无人工 confirm）；一条重复任务触发 skill 迭代（version 升级）。
- **维度2**：一条架构级候选在 `confirm` 前被拦截、走 HITL；一条已结晶技能在观察期触发回归指标超阈值，自动 `dissolve` 并保留教训。

---

## 3. 依赖与前置

- 依赖 Phase 15 已落地的 `Validator`、`Evaluator`、`SandboxManager`、HITL `confirm`。
- 依赖 Phase 11 的 `judgment`（JEV `score` 原语 + 主 LLM 回退），用于摘要提炼、重要性打分、语义路由、SOP 提炼。
- 依赖 Phase 17 的语义记忆落盘 + `session_id` 维度（固化按 session 归组）。
- 依赖 `permission` 的效应分析（EffectTracker 已存在）做「技能库 vs 架构」风险域判据。
- **首步契约核对**：`MemoryEntry` 字段（protocol.py:20-32）+ `store.read/compact`（store.py:56-118）与 `doc/03-interfaces/memory-interface.md` 对齐；`Skill` 字段（skills/models.py:15-26）+ `SkillLibrary/SkillRouter`（library.py / router.py）与 `doc/03-interfaces/skills-interface.md` 对齐后再动手（沿用 phase-17 回填惯例）。

---

## 4. 首步任务（最小可验证增量）

1. `protocol.py` `MemoryEntry` 增 `importance: float = 0.0`、`kind: Literal["episodic", "semantic"] = "episodic"`（放在 `session_id` 之后，字段顺序与接口文档同步）。
2. `store.py` `read` 排序 key 由单 `relevance` 改为多因子加权函数（新增 `_rank(e, query)` 私有方法）。
3. 同步回填 `memory-interface.md` 的 `MemoryEntry` 字段清单，保持代码↔文档一致。

完成后门禁全绿即视为「记忆字段 + 多因子检索」地基就绪，再推进摘要压缩与固化；随后进入维度1（SOP 提取器 → 语义路由 → Skill 迭代）。

---

## 5. 实现顺序（拓扑序，一次只做一项）

1. **memory 字段扩展**：`MemoryEntry` 增 `importance` / `kind`；`write` 时默认 `kind="episodic"`。
2. **检索多因子化**：`store.read` 排序改用 `_rank`（relevance × recency × reuse_count 对数 × importance）；`reuse_count` 在 `read` 命中后 +1（复用即强化）。
3. **摘要式压缩**：`store.compact` 注入 Compactor 时，由「score 保留/丢弃」升级为「按 session/主题聚合 + LLM 提炼摘要」，产出 `kind="semantic"` 条目（content 为摘要，source 保留原始 trace_id 列表，可逆）。
4. **固化 consolidation**：新增 `Consolidator`（L2，复用 judgment/LLM），把高 `reuse_count` / 高 `importance` 的 episodic 条目提炼为 semantic 事实/教训，触发时机 = session 结束 / 阈值超限。
5. **遗忘 forgetting**：新增衰减循环，`score = recency × (1 + log reuse_count) × importance` 低于阈值的条目迁移到归档层（不 delete，`audit` 可见）。
6. **维度1 SOP 提取器**：新增 `SopExtractor`（skills 层），从同类任务轨迹提取 SOP → 提炼 `Skill`（instructions/task_types），经 `SkillLibrary.register` 入库；LLM 提炼走 judgment（fallback LLM）。
7. **维度1 语义路由**：`SkillRouter` 评分升级为语义匹配（JEV 打分 + fallback LLM），词法保留 fast path；`_record_miss` 未命中仍写 L2（供后续沉淀）。
8. **维度1 Skill 迭代**：记录 skill 命中 + 执行反馈，发现不完善触发迭代（`version` 升级 + `ABResult` 对比），迭代后自动发布。
9. **维度2 confirm 收口**：`engine` 确认架构级候选（`kind="plugin"`）一律 `confirm`，不引入低风险自动结晶；`risk_level` 仅用于「技能库 vs 架构」风险域判据。
10. **auto-dissolve 自动回滚**：结晶后登记观察期，evaluator 持续采样回归指标，超阈值自动 `dissolve`，并写审计 trace。
11. **遗留欠账收口（按真实依赖，2026-10-04 修正序）**：
    ① **P0 + P0b** 接装配器 + 两级 Core.md 注入 + 人格→L0 ✅ **已完成**
    （2026-10-04；B2/B5/B6 已随之在生产生效）
    → ② 交付物 **#1/#2**（`importance`/`kind` + 多因子重排，**一并接 C7 embedder + 缓存策略**，先落 ADR）
    → ③ **B5** ✅ **已完成**（2026-10-04，`_trim` 跳过语义 + skills 余量）；
      **B6** 判为「按架构如此」**关闭**（装配是 Reason 前一次性步骤；残留并入 A3）
    → ④ `0040-memory-embedding-config` ✅ **已完成**（2026-10-04：`llm.embedding_model`
      配置旋钮（advanced 暴露面）+ 组合根以该模型另构造 provider → `LLMEmbedder` → 注入
      `MemoryStore`；未设置/不可达回退词法。ADR-0045 转 Accepted）
    → **#6 SOP 提炼** ✅ **已完成**（2026-10-04，change `0043-sop-skill-extraction`；
      ADR-0048 Accepted）
    → **#7 语义路由** ✅ **已完成**（2026-10-04，change `0044-semantic-skill-routing`；
      ADR-0049 Accepted；**B4 判冗余 → 删除 `ContextPack.skills`**）
    → **#8 Skill 迭代** ✅ **已完成**（2026-10-04，change `0045-skill-iteration`；ADR-0050
      Accepted；命中注入 `instructions` + `(id, version)` 反馈 + 复用 `VersionManager` 灰度/A/B）
      → **#9/#10**（`risk_level` 强制 confirm + 观察期自动 dissolve）。
    A1/A3 已清账（✅）。

---

## 6. 契约对齐

- `MemoryEntry`（protocol.py:20-32）：新增字段 `importance`/`kind` 为**默认值向后兼容**，不破坏现有构造调用；`memory-interface.md` 同步字段清单。
- `MemoryStore.read/compact/migrate/audit`（store.py:56-118 / protocol.py:42-65）：签名不变，仅排序算法与 compact 语义升级；`compact` 无 Compactor 时仍返回 `None`（保持现状兼容）。
- `Skill`（skills/models.py:15-26）：`instructions`/`version`/`status`/`ABResult`（models.py:29-35）已存在，本 Phase 复用，不破坏字段；`skills-interface.md` 同步「SOP 提取 + 语义路由 + 迭代」的接口声明。
- `SkillLibrary.register/check_preconditions`（library.py:23-65）：签名不变，SopExtractor 复用注册 + schema 校验 + 前置条件。
- `SkillRouter.route/_score`（router.py:41-62）：`route` 签名不变，`_score` 内部升级为语义匹配（词法 fast path 保留）；`_record_miss` 语义不变。
- `SkillCrystallizer.crystallize/dissolve`（crystallizer.py:40-60）：`dissolve` 增加「自动触发」调用点，签名不变。
- 进化四阶段（engine.py:34-177）：diagnose→propose→validate→evaluate 顺序不变；`confirm` 分支**保持必审**（维度2 架构级），仅新增观察期 auto-dissolve 采样。
- `Proposer.propose`（proposer.py:25-34）：签名不变，`status="pending"` + `kind` 区分「技能库 vs 架构」语义保持。
- **JEV fallback**（judgment/router.py）：决策统一走 `DecisionRouter.decide`——JEV 优先、无 JEV/不可达/超时/低置信度自动 fallback 主 LLM，本 Phase 不新增决策代码。
- 风险域判据复用 `permission` 效应分析（EffectTracker 已存在，见 store.py:42/78）；不新开 permission 能力。
- 所有 spec/interface 契约以仓库原文为准，速查 `contracts_summary.md`。

---

## 7. 门禁验收

提交前四者必须全绿：

```bash
ruff check src tests
ruff format --check src tests
pyright
pytest -q
```

补充测试要点（`tests/`）：
- `test_memory_consolidation`：episodic → semantic 提炼正确，semantic 条目保留 source trace_id。
- `test_retrieve_multifactor`：reuse_count/importance 高者排序靠前，recency 衰减生效。
- `test_compact_summarizes`：注入 Compactor 后 `compact` 产出摘要条目（非布尔）。
- `test_forgetting_archives`：低分条目迁移归档且 `audit` 可查、`read` 不再命中。
- `test_sop_extract`：同类任务轨迹提取出 `Skill`（instructions=SOP 步骤、task_types 归组正确）。
- `test_semantic_route`：语义路由对「类似任务」命中对应 Skill（词法 fast path 不误伤）。
- `test_skill_iterate`：重复任务发现 skill 不完善触发迭代（version 升级 + ABResult）。
- `test_confirm_required`：架构级候选（`kind="plugin"`）在 `confirm` 前不落库、走 HITL。
- `test_auto_dissolve`：观察期回归指标超阈值自动 dissolve。

---

## 8. 提交规范

- 单次提交：`feat(memory+skills+evolution): 记忆固化自动化（摘要压缩/固化/遗忘）+ 技能进化双维度（维度1 SOP 技能库全自动进化 + 维度2 架构级人工审核收口）`
- 变更范围：`src/core/memory/`（protocol / store / 新增 consolidation、forgetting）、`src/core/skills/`（新增 SopExtractor + 语义路由 + Skill 迭代）、`src/core/evolution/`（confirm 收口 + auto-dissolve）、`doc/03-interfaces/memory-interface.md`、`doc/03-interfaces/skills-interface.md`；测试同步。
- 不新增三方依赖；不触碰 Phase 15 已拍板的 HITL `confirm` 公开语义（维度2 保持必审，仅收缩维度1 技能库的触发范围）；不回改 `TaskScheduler` 断点续跑 / checkpoint。
