# Phase 39：记忆闭环的另一半 —— 语义遗忘面 ＋ SOP 技能退役（批次 `0204`~`0205`，2 change）

> **状态**：✅ **全闭**（2026-10-11；2 条 change 逐条独立收口：各自 change 目录 / ADR / 规格 delta /
> 四门禁 / 手工归档 / 单次提交）。
> **来源**：2026-10-11 用户在「四类记忆是否闭环」的取证结论上追认开工。取证（Explore agents ＋
> 直接读码）确认四类记忆**没有一类四闭**，其中两处是**能力级真缺口**：① **语义记忆缺遗忘** ——
> `forget()` 守卫把 `kind="semantic"` 条目**永不遗忘**，且这是**规格写死的**；② **程序记忆缺溶解**
> —— `Skill.status` 取值域含 `deprecated` 而**生产无路可置**。⇒ 用户裁决 **两条全做**。
> **为什么是一批而非一条**：两缺口属**两个不同 capability**（`memory` / `skills`），实现面、规格面、
> 消费面彼此隔离 ⇒ 沿 **Phase 34~38 先例**：**一个批次、多条 change**，每条仍各自 change / ADR /
> delta / 四门禁 / 单提交。**执行顺序 = 编号顺序**（`0204` 只碰 `memory`、风险低；`0205` 触及
> `skills` 生命周期 ＋ ADR-0011 边界，风险高）。
>
> **红线（全批次）**：主方向封存 `exclude_source_prefixes=("beast.","pet")`（`runtime.py`
> **逐字不动**，phase-26）；密钥**只引用不读取**、**绝不**进日志/记忆（留痕**只报条目 id / 组键**，
> **绝不回显正文或取值**）；所有写效应经 `EffectTracker` 可回滚（归档用 `migrate`，**不物理删除**）；
> **每条新行为缺省关 ⇒ 既有路径逐字不变**（本批两条的**主要验证锚**）；零三方依赖；
> `config*.yaml` / `.claude/settings*.json` / `uv.lock` 等**不提交**。

---

## §0 用户裁决的五个设计岔口（AskUserQuestion，2026-10-11）

| # | 岔口 | 裁决 |
|---|---|---|
| 1 | **批次范围** | **两条全做**（语义遗忘 ＋ SOP 退役） |
| 2 | **语义遗忘面** | **仅派生事实**（`source ∈ {extraction, relation}`），摘要类（`{compaction, context}`）**永久豁免** ⇒ change `0204` |
| 3 | **SOP 退役触发器** | **迭代连续退化 → 自动退役**（**自动**，不依赖人工确认 —— 守红线「维度1 技能库/SOP 全自动」）⇒ change `0205` |
| 4 | **缺省开关** | **缺省关、显式开启**（既有路径逐字不变）⇒ 两条 |
| 5 | **退役后复活** | **粘性退役，需显式复活**（重抽不得自动复活；复活仅经 `SkillLibrary.activate`）⇒ change `0205` |

---

## §1 批次总览（执行顺序 = 编号顺序；风险递增）

| # | change（归档目录） | capability | 一句话 | ADR | 台账 | 测试基线 |
|---|---|---|---|---|---|---|
| 1 | `0204-semantic-forgetting` | `memory` | 派生事实（`keyfact.*`/`relation.*`）按**同一衰减判据**参与遗忘；摘要类语义条目**永久豁免**；新构造参 `semantic_forgetting`（缺省关） | ADR-0194 | E141 | 2294 → 2310（+16） |
| 2 | `0205-sop-skill-retirement` | `skills` | `SkillLibrary.deprecate`（镜像 `activate`，可逆）＋ `SkillIterator` **连续退化达阈自动退役** ＋ **粘性防复活**（重抽不得复活）；缺省关 | ADR-0195 | E142 | 2310 → 2327（+17） |

**批次合计**：测试基线 **2294 → 2327**（**+33**，与两条预估 +16/+17 一致）；
`openspec validate --all` **32 passed / 0 failed**；四门禁（`ruff check` / `ruff format --check` /
`pyright` **0-0-0** / `pytest -q`）**逐条全绿**。

**共同形态**：两条都**不新开面**而**收窄/镜像**既有面 —— `0204` 收窄 `记忆遗忘` 的豁免面（本仓
首次对既有 Requirement 做 MODIFIED / 全量替换）、`0205` 逐字镜像既有 `activate` 做 `deprecate`；
两条都**复用既有判据**（同一衰减评分 / 同一阈值 / 同一 L4 去向 / 同一可撤销面；同一 `_restore_status`）
⇒ 改动面最小、零可漂移判据。

---

## §2 账目（E141~E142，逐条根因 → 修法）

| 台账 | 根因（一句话） | 修法（一句话） | 归档 |
|---|---|---|---|
| **E141** | **语义记忆只增不减 ⇒ 语义一类的遗忘面缺半**：`forget()` 守卫（`store.py:622`）为 `entry.kind != "episodic" or entry.layer != "L2" ⇒ continue` ⇒ `kind="semantic"` **永不遗忘**；且这是**规格写死**（`memory/spec.md:391-392` SHALL ＋ Scenario `提炼产物与元策略不被遗忘` 断言）⇒ 结构化抽取的 `keyfact.*`（`extraction`）/ `relation.*`（`relation`）**只增不减**，`read()`/`_gather_facts` 无层过滤（L4 仅加性降权 0.2）⇒ 陈旧派生事实持续占注入预算 | **收窄既有 `记忆遗忘` 的豁免面**（**本仓首次 MODIFIED / 全量替换**）：从「**全部** semantic」收窄为「**摘要类** semantic」，放行「**派生事实类**」；**开关缺省关**（构造参 `semantic_forgetting=False` ＋ 配置 `memory.semantic_forgetting`）⇒ 缺省时派生事实与摘要类**同**不受影响（逐字不变）；**复用同一判据**（`_decay_score` ＋ `_FORGET_THRESHOLD` ＋ `migrate`→L4 ＋ `forgetting.<id>` 效应）；守卫用**短路布尔**（不新增 `If` 嵌套，`0203` 教训）＋ 常量 `_FORGETTABLE_SEMANTIC_SOURCES` 与 `_GATE_EXEMPT_SOURCES` 并列并**注释点明二者是不同面**（**豁免评分 ≠ 豁免遗忘**）；`forget()` **签名不动** ⇒ 三处零参调用点逐字不变 | `0204` / ADR-0194 |
| **E142** | **程序记忆只能结晶、不能溶解 ⇒ SOP 技能一旦自动 `active` 即永久可路由**：`Skill.status` 取值域含 `deprecated` 但**生产无路可置**（`decide()` 单次退化只丢草稿，`iteration.py:135` 注释明写「不置 deprecated」；`EvolutionEngine.dissolve` 的 id 前缀 `skills.evolution.` `engine.py:227` 永不命中 `skills.sop.<hash>`；`SkillLibrary` 无 `deprecate`/`retire` 面；`SkillCrystallizer.dissolve` 是**死代码**）⇒ 与 P2「可逆」及「失败即溶解」相悖 | **`skills` 自有的自动退役**：`SkillIterator` 逐技能统计**连续** A/B 退化（一次提升**归零**），达阈 `RETIRE_AFTER_DEGRADATIONS`（缺省 3）自动 `SkillLibrary.deprecate`（**镜像 `activate`**，可逆 trace `skills.deprecate`）；计数**折叠进 `decide()` 既有分支** ⇒ 运行时钩子零改动；**粘性防复活**守卫在 `sop.py::observe`（**不改 `register` 通用覆盖语义**）；**开关缺省关**（构造参 `retire_after=None` ＋ 配置 `skills.retirement`，**全仓首个 `skills.*` 键**）⇒ 关闭时 `decide()` 逐字不变；**ADR-0011 边界调和**：evolution 的「观察期回归自动溶解」依赖留出集基准（生产 `Evaluator` 无基准 ⇒ `freeze`）⇒ 对 SOP **结构性不可达** ⇒ 本次与它**判据/对象/数据源三重不同、不重叠** | `0205` / ADR-0195 |

---

## §3 逐 change 收口要点

### `0204` 语义遗忘面（`memory` / ADR-0194 / E141）
- **规格**：`memory` **MODIFIED**「记忆遗忘（forgetting）」（全量替换）＋ **MODIFIED** Scenario
  `提炼产物与元策略不被遗忘`（GIVEN 收窄、标题不动）＋ **ADD** 3 Scenario ⇒ canonical
  **15 req 不变 / 108 → 111 scen**（归档断言：0 Requirement-header 丢失 / 0 Scenario-title 丢失）。
- **实现**：`store.py`（`_FORGETTABLE_SEMANTIC_SOURCES` ＋ 构造参 ＋ `forget()` 守卫 ＋ docstring）、
  `manager.py`（`memory.semantic_forgetting` ＋ `semantic_forgetting()`）、`runtime.py`（接线）。
- **反证**：摘掉 `self._semantic_forgetting and` 短路项 ⇒ 缺省关零回归锚 ＋ 翻转锚 **2 红**；复原即绿。
- **局限**（§3 ADR-0194 行）：归档 ≠ 移出注入面；只归档「不再被重抽」的事实；缺省关使能力惰性；
  首次 MODIFIED 既有 Requirement；配比面无新键。

### `0205` SOP 技能退役（`skills` / ADR-0195 / E142）
- **规格**：`skills` **MODIFIED**「技能迭代闭环」（定夺 bullet 收窄为**单次**失败 ＋ 前向引用）＋
  **MODIFIED** Scenario `A/B 退化丢弃新版本`（GIVEN 收窄、标题与 THEN 逐字保留）＋
  **ADDED**「SOP 技能退役」＋ 6 Scenario ⇒ canonical **10 → 11 req / 49 → 55 scen**（0 丢失）。
- **实现**：`library.py`（`_DEPRECATE_TRACE` ＋ `deprecate` ＋ `_track_deprecation`）、
  `iteration.py`（`RETIRE_AFTER_DEGRADATIONS` ＋ 构造参 ＋ `_degradations` ＋ `decide()` ＋
  `_count_degradation`）、`sop.py`（`observe` 防复活守卫 ＋ `_is_retired`）、`manager.py`
  （`skills.retirement` ＋ `skill_retirement()`）、`runtime.py`（接线）。
- **反证**（**2 组**）：① 摘掉 `decide()` 退化分支的 `deprecate` 调用 ⇒ 连续退化 / 可撤销 **2 红**；
  ② 摘掉 `sop.py` 粘性守卫 ⇒ 防复活锚 **1 红**。两处复原即绿。
- **局限**（§3 ADR-0195 行）：退役不可自动复活；连续计数是进程内状态；可回滚仅当注入 tracker；
  三处既有旁路各置 `status` 却不共享本次 trace（不动）；`_index` 既有重复 bug（不修）；退役 ≠ 删除。

---

## §4 显式不做（全批次）

- **不**给 `SkillLibrary.register` 加通用「拒绝覆盖 deprecated」逻辑（会影响 beast / notes / evolution）。
- **不**修 `SkillLibrary._index` 的既有重复 bug（超范围，仅登记）。
- **不**把 SOP 退役改道走 `EvolutionEngine`（留出集基准生产不可达 ＋ 命名空间不同 ＋ 判据不同）。
- **不**改 `SkillCrystallizer`（死代码）—— 走 `SkillLibrary.deprecate` 最小面。
- **不**让归档的派生事实退出注入面（保既有 L4 语义；如需再立 change）。
- **不**新增「遗忘什么 / 退役什么」的配置面键（开关只表达「开不开」，判据面逐字复用）。

---

## §5 收口与验证

- **四门禁（直连二进制，不用 `uv run`）**：`.venv/bin/ruff check src tests` ·
  `.venv/bin/ruff format --check src tests` · `/home/harry/.praisonai/venv/bin/pyright`（**0-0-0**）·
  `.venv/bin/pytest -q`（**2327 passed**）。
- `openspec validate --all` ⇒ **32 passed / 0 failed**；两条 change 各经
  `python3 /tmp/openspec_archive.py <change-NAME>` 手工归档（断言 0 Requirement-header 丢失 /
  0 Scenario-title 丢失）后 `mv` 进 `doc/openspec/changes/archive/`。
- 每条**单次提交**（尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`）：
  `0204` → `feat(memory): 语义遗忘面 —— 派生事实参与遗忘（change 0204 / ADR-0194 / 台账 E141）`；
  `0205` → `feat(skills): SOP 技能连续退化自动退役 + 粘性防复活（change 0205 / ADR-0195 / 台账 E142）`。
- 文档面：`doc/04-testing/test-cases.md` §117/§118 · `coding-plan/known-risk.md` §1/§3 ·
  `doc/02-modules/memory.md` §3.10 / `doc/02-modules/skills.md` §3.5 · ADR 变更追踪表两行 · 记忆更新。
