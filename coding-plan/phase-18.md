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
- **B4 `ContextPack.skills` / `pending` 恒空——前提部分不成立，判为冗余**：技能**已经**进
  prompt——planner 有 `skill_router` 回调（`runtime.py:191` → `planner.py:132 _skill_hints`
  → 「可用技能」块）。缺口仅是 `ContextPack.skills` 字段恒空（`build` 从不填充），**无功能
  空洞**。落点＝并入交付物 #6/#7（SOP/语义路由）时顺带填充，或直接判定冗余删除；
  **不单列为独立任务**。
- **B5 `_trim` 保序截断**：`budget.py:56-64` 按顺序取前 N 到预算即止，非按相关度裁剪
  → 高价值项可能被后到的低价值项挤出。落点＝预算裁剪改为「按多因子得分排序后截断」。
  **依赖 P0 生效。**
- **B6 仅 reason 阶段装配**：`assembler.build` 唯一调用点＝planner `reason`（`planner.py:124`）
  → perceive/act 阶段无信息供给。落点＝按需为 perceive（首轮召回）/ act（工具选择）扩展装配
  阶段。**依赖 P0 生效。**
- **P0b 人格 → L0 记忆层** ✅ **已完成**（2026-10-04）：`build_runtime` 在装配画像后，将
  人格分区以稳定 id `core-profile:personality` **幂等**写入 L0（`source=core-profile`）；
  测试锁定幂等（两次装配同 id 不重复）。L0 优先级最高，读时随候选带出、受预算截断约束。
- **A1 `LoopContext.memory` 遗留字段** ✅ **已完成**（2026-10-04，commit db204dc）：全仓确认
  无消费方后删除字段，同步 `loop-interface.md`（连带清除文档里的幽灵类型 `MemoryPack`）。
- **A3 `stage` 装饰性参数** ✅ **已完成**（随 B2 / change 0038）：`context-interface.md` 与
  `context/spec.md` 已如实标注 stage「暂不参与事实选择」。仍可选：赋予阶段化权重（留待按需）。

---

## 2. 里程碑验收

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
    → ③ **B5/B6**（随装配器阶段化）
    → **B4** 并入 #6/#7 或判冗余删除（不独立排期）。
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
