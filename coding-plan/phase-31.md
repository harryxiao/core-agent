# Phase 31：进化引擎「生产验证门名副其实化」—— RSI 能力缺口**提案**（非缺陷账本）

> **状态**：✅ **全闭（切片 1 + 切片 2）**（2026-10-06 用户裁决 ⇒ 立账为能力缺口 + 拆两次；**切片 1（G4+G3 数据面）**＝change `0119` / ADR-0112：基准集/基线落盘 + 真实留出评分 + 口径版本；**切片 2（G1+G2 判定面）**＝change `0120` / ADR-0113：真实 review + 真实运行时测试 + `GATE_CALIBER` 递增 —— **G1–G5 全闭**，`rejected` / `rollback` / `frozen` 三态**生产可达**；**遗留**见 §8）
> **定性**：能力缺口**提案**（非缺陷账本；承接 `phase-27.md` §7 遗留清单第①条 / ADR-0105 已知局限①）
> **定性**：phase-27 落地**冻结门**（`EvolutionExecutor`）时如实登记：生产装配的 `Validator()` / `Evaluator()` 是**恒通过桩** ⇒ 进化闭环四阶段中的**第 3（验证门）与第 4（留出评测）在产线上恒为常量**。当时判「另一件事」（波及既有 `confirm`/`crystallize` 与观察期基线）**不并入**该切片。本 Phase 把它**立账**：**须用户裁决 → 规格先行 → ADR** 之后才能拆 change，**不得**以缺陷修复名义静默实施。
> **与 phase-27 的关系**：phase-27 让**实施面**（补丁落地的四道门禁）有了唯一真门；本 Phase 要让**结晶面**（候选发布的验证门 + 留出评测）名副其实。两者是**两条不同的门**，共用 `GATE_COMMANDS` 真源但不可互替。

---

## 0. 结论总览

| 编号 | 缺口 | 判死证据（行号） | 定性 | 修复方向 |
|---|---|---|---|---|
| **G1** | 生产 review 判定**恒真** | `evolution/validator.py:15-16` `_review_pass` 恒 `True`；`:34` 缺省注入；`:40` `review_ok and all(...)` | 恒通过桩 | 接真实 review（LLM 面已存在于 `evolution/author.py`） |
| **G2** | 生产运行时测试**恒空** | `validator.py:19-20` `_no_tests` 返 `{}`；`:40` `all({}.values())` ≡ `True` | 恒通过桩 | **复用**冻结门同源（`ci_cd/pipeline.py:25 GATE_COMMANDS` + `:47 SubprocessGateExecutor`），**不得另立第二份门禁清单**（spec `:273`） |
| **G3** | 生产留出评测**无 `score_fn`** | `evaluator.py:98` 缺省 `None`；`:131-134` `_held_out_score` 缺省返 `0.0` | 恒 `publish` | 注入真实打分器（注意：**不接实施验证路径**，spec `:273-274`） |
| **G4** | **基准集 / 基线无生产装配**（G3 的**前置**） | `evaluator.py:20-40` `BenchmarkRegistry` 为**进程内 dict**（`:24-25`，**无 `path`** ⇒ 无法落盘）；`baseline_score` 缺省 `0.0`（`:39-40`）；全仓 `set_baseline` / `score_fn=` **零生产调用点**（仅 `tests/test_evolution.py:129-131/226-232`、`test_phase15.py:122`） | **即便修好 G3 也仍旧恒 publish** —— `held_out(≥0) < baseline(0.0) - 0.0` 恒为假 | 基准集落盘（有 `_skill_state_path` 先例）+ 基线采集 + 组合根注入 |
| **G5** | `rejected` / `rollback` 分支**生产不可达** | `engine.py:98-107`：门恒过 ⇒ `status="rejected"`（`:101-103`）与 `="rollback"`（`:106-107`）**在生产永不触发** | **可执行判据**（本 Phase 的验收锚点） | 修复后应能**构造**任一分支 |

> **共同口径**：引擎**确实消费**结论 —— `engine.py:98-99` 读 `gate.passed`、`:104-106` 读 `eval_report.verdict`（`:161`/`:167` 复核面亦然）。故缺口**不在接线**，在**产出的值恒为常量**。这与 phase-27 的形态不同：那里是「闸门不存在」，这里是「闸门在、门禁全开」。

> **切片 1 后的状态（2026-10-06，change `0119` / ADR-0112）**：**G4 已闭**（基准集/基线落盘可跨进程读
> + 组合根注入）；**G3 已闭**（留出分由绑定基准经执行器真实产出；无法评测 ⇒ `freeze` fail-closed）；
> **G5 锚点已达**（`frozen` 生产可达，`rollback` 可构造）。**未闭**：G1/G2（`validator.py` 逐字未动
> —— 属切片 2）；产线**执行器映射**未接 ⇒ 候选恒 `frozen`（**这是「不再凭空发布」的有意结果**，
> 见 §7 与 ADR-0112 已知局限①）。

> **切片 2 后的状态（2026-10-06，change `0120` / ADR-0113）**：**G1 已闭**（review 由**结构化审查者**
> 产出：`build_review_prompt` 审候选自洽性、模型调用经组合根 `review_with(_llm_text)` 注入 —— 复用
> `author.py` 接缝，evolution 仍不 import LLM 抽象）；**G2 已闭**（运行时测试 = **按标记派生**的结晶面
> 门禁子集 `lint` + `test`，命令仍只有 `GATE_COMMANDS` 一份；执行面复用 `SubprocessGateExecutor`）；
> **缺省 `Validator()` 改为不得放行**（fail-closed，与切片 1 的 `Evaluator()` 同型）；`GATE_CALIBER`
> **1 → 2**（旧口径候选投放时 `GATE_CALIBER_STALE`）。**G5 验收锚点实测**：`rejected` 生产可达
> （装真判据后未过门即 `status="rejected"`，此前恒 `pending`）。**代价照实登记**：冷路径**同步**跑
> 子进程门禁（数十秒，仅在维护节拍 + 阈值命中 + 有证据时；reopen = 冷路径异步化）。

---

## 1. 一手核实（证据与行号）

### 1.1 Validator 在生产恒通过

`src/core/evolution/validator.py`：`_review_pass`（`:15-16`）恒 `True`、`_no_tests`（`:19-20`）返空 dict，两者是 `__init__`（`:28-35`）的**缺省**；`validate`（`:37-42`）判 `passed = review_ok and all(test_results.values())` —— **空 dict 的 `all()` 为真** ⇒ `passed` 恒 `True`、`review` 恒 `"通过"`。

生产装配实证：`src/core/runtime.py:589-590` 为 `validator=Validator(), evaluator=Evaluator()` —— **无参**（不注入 `review` / `tests` / `score_fn` / `registry`）。

> **订正（2026-10-06）**：本节行号是**立账时**的快照；`validator.py` 已由 change `0120` 重写（恒通过桩
> 已删，两个判据生产者改为注入 + fail-closed），`G1/G2` 已闭 —— 见文首状态与 §0 两段状态块。

### 1.2 Evaluator 在生产恒 publish

`src/core/evolution/evaluator.py`：`Evaluator.__init__`（`:85-100`）缺省 `score_fn=None`（`:98`）；`_held_out_score`（`:131-134`）在无 `score_fn` 时**返 `0.0`**；`evaluate`（`:102-117`）取 `baseline = registry.baseline_score(...)`（`BenchmarkRegistry` 是**进程内空 dict**，`:39-40` 缺省恒 `0.0`）⇒ `held_out(0.0) < baseline(0.0) - margin(0.0)` 为**假** ⇒ 恒 `EvalReport(passed=True, verdict="publish")`。

### 1.3 规格原文对照 —— **判据争议点（须裁决）**

| 读法 | 依据 | 结论 |
|---|---|---|
| **(a) 字面满足** | `evolution/spec.md:122-123`「系统 SHALL 对候选执行 review + 运行时测试，通过才允许发布」——生产**确实**调用 `Validator`/`Evaluator`，且引擎**确实**按 `passed`/`verdict` 分支；缺省桩是**可插拔缺省值**，属组合根的**装配选择** | **非违约** |
| **(b) 实质为空** | 同 spec `:154-155`「SHALL 提供**可落地**的评测基建（基准集 + 评测运行器 + 指标对比基线），支撑验证门与留出评测的**工程化执行**」——生产**既无基准入库路径**（§1.4）、**又无基线采集**、**又无 review/tests 生产者** ⇒ 三道 Requirement 的产出**恒为常量** ⇒ "可落地 / 工程化执行" 落空；且与总纲 `core_harness_architecture.md:150-153/158`「验证通过 ⇒ 产出不可变世代」的承诺背离 | **能力缺口** |

⇒ **本 Phase 的定性取决于此裁决**（与 phase-27 的 E40/E41「架构承诺 vs 规格明文边界」同型）。

### 1.4 已落地的部分（本轮**不重复造**）

> **订正（2026-10-06，切片 1 落地后）**：下列「已落地」的**类**仍然齐备，但 §1.4 末句「缺的只有
> **生产装配 + 数据面**」已由 change `0119` 补上**一半** —— 基准集/基线**已落盘**（`BenchmarkRegistry(path=…)`
> → `$CORE_STATE_DIR/evolution-benchmarks.json`，跨进程可读）、`Evaluator` 已接**真实打分器**
> （`BenchmarkScorer`，逐样本真实执行）。**仍缺**：基准的**执行器映射**（`task_type` → 可调用体）
> 生产未接（⇒ 产线判 `frozen`，见 §7 切片 2 与 ADR-0112 已知局限①）、以及 G1/G2 的 review / tests
> **生产者**（切片 2）。

- **评测基建的类齐备且有测试**：`BenchmarkRegistry`（`evaluator.py:20-44`：`register`/`set_baseline`/`baseline_score`/`list`）、`QualityEvaluator`（完成度 / 正确性 / 轨迹三分，`:30-77`）、`evaluate_batch` + `Semaphore` 并发上限（`:123-129`，对齐 spec `:148-151`）。
- **引擎消费面齐备**：`engine.py:98-107` / `:161` / `:167`。
- **门禁真源齐备**：`ci_cd/pipeline.py:25 GATE_COMMANDS` + `:47 SubprocessGateExecutor`（ADR-0086）。
- **缺的只有「生产装配 + 数据面」**：基准从哪来、基线怎么采、review 判据是什么。

---

## 2. 范围与定位

- **本 Phase 要做的**：让 `Validator` / `Evaluator` 在**生产装配**下产出**真实判定**，使「未过门 ⇒ 不发布」在**结晶路径**上可发生。
- **本 Phase 明确不做的**：① **不改** `crystallize` 的 `accepted` 诚实语义（ADR-0100 —— 「已批准、待人工实施」**不回退**为 `published`）；② **不**把 `Evaluator` 接进**实施验证**（spec `:273-274` 明文「留出评测**不**参与实施验证——本 Requirement 只承诺冻结门」）；③ **不**另立门禁清单（spec `:273`）；④ **不**动冻结门（phase-27 已闭）。
- **收益（诚实版）**：本 Phase **不**让系统凭空产出世代（发布仍待人工 `confirm`）；收益是恢复**拒绝能力** —— 今天**任何**候选都过门，`rejected` / `rollback` 分支**生产不可达**（G5）。修好后「不合格候选被挡在门外」这句 spec 承诺才成立。

---

## 3. 落地拆解（规格先行）

> **顺序**：用户裁决 → 规格先行（`evolution` spec：验证门 / 留出评测 / 评测基建三处 Requirement 补**生产者与数据面**条款 + 可执行场景）→ ADR → 测试先行（红：构造 rejected / rollback）→ 实现 → 四门禁全绿 → 手工归档 → 台账回填。

### 3.1 G4 基准集与基线（**先做**，G3 的前置）

- `BenchmarkRegistry` 增可选 `path`，落盘为单文件 JSON（**先例**：`MarketIndex(path=…)` / `PendingQueue(path=…)` / `_skill_state_path`，ADR-0103/0105）；损坏 ⇒ `warn` 降级空表。
- 基线采集路径：候选**未**改动的既有插件，以同一评测器打一次分即基线（`set_baseline`）——须裁决「基线由谁采、何时采、跨进程存哪」。

### 3.2 G1/G2 验证门的真实判据

- `review`：可复用 `evolution/author.py` 的 LLM 面做结构化 review（`kind`/`target_plugin`/`delta` 是否自洽）。
- `tests`：**复用** `SubprocessGateExecutor` + `GATE_COMMANDS` 的**子集或全量**——**必须**裁决「结晶面跑哪几道门」（全量 = 慢但与实施面同源；子集 = 快但需**规格写明**哪几道，否则又是一份隐含清单，触 spec `:273` 红线）。

### 3.3 G3 留出评测的真实打分

- `score_fn` 接 `QualityEvaluator`（需 `expected` ⇒ **依赖 G4 的基准集**，故 G4 先行）；`margin` 取现行 spec `:350` 的**绝对分差**口径（默认值须裁决，今天 `0.0` 意味「分毫不许退」）。

### 3.4 门禁

四命令（**直连二进制，禁 `uv run`**）：`.venv/bin/ruff check src tests` / `.venv/bin/ruff format --check src tests` / `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）/ `.venv/bin/pytest -q`。

---

## 4. 裁决点（须用户拍板后规格先行）

1. **G1–G5 定性**：(a) 非违约「装配选择」保持现状 / (b) **立账为能力缺口并按本 Phase 落地**（§1.3）。
2. **结晶面跑哪几道门**：全量 `GATE_COMMANDS`（慢、与实施面同源）／子集（快、须写进规格避免隐含清单）／只跑 review 不跑 tests。
3. **基准集来源**：人工注册（运维面）／从既有成功轨迹自动沉淀（**须防自我强化**：用被评对象的历史打分当基准 = 自证）／暂不采基线只跑绝对阈值。
4. **基线持久化位置**：`CORE_STATE_DIR` 单文件（先例）／随候选台账（`PendingQueue`）／暂不落盘（仅进程内，**等于承认跨进程评测无基线**）。
5. **`reuse_count` / 观察期基线**：ADR-0105 决策⑩ 记「波及既有 `confirm`/`crystallize` 与观察期基线」——须确认修门后**是否**需同步调整观察期口径（否则可能出现「历史候选在新口径下集体未过门」）。
6. **切片**：一次做完（G1–G4 + 可执行判据 G5）／拆两次（先 G4+G3 数据面，后 G1+G2 判定面）。

### 4.1 裁决参考意见（供拍板，含推荐结论）

> **总开关**：第 1 点若取 (a) 保持现状，则 2–6 全部作废、本 Phase 转销账登记。以下均以「选 (b) 立账落地」为前提。

1. **G1–G5 定性 → 建议 (b) 立账为能力缺口**：`runtime.py:589-590` 是无参 `Validator(), Evaluator()`，**连注入点都没有**——「装配选择」要成立须「有得选」，这里没有；且 G5 `rejected`/`rollback` 生产不可达 ⇒ 「不合格候选被挡在门外」**实质不成立**。与 phase-27 E40/E41 同型，应保持同一裁决口径。
2. **结晶面跑哪几道门 → 建议「子集」**：核心门 = `pytest`（回归）+ `ruff check`（轻量）；`format`/`pyright` 属代码卫生，与「能否发布」相关性弱，排除。实现 SHALL 从 `GATE_COMMANDS` **按标记派生**子集，SHALL NOT 硬编码第二份字符串清单（spec `:273` 红线），且 spec 明文写出「哪几道进结晶面、为什么」。
3. **基准集来源 → 建议「人工注册 + 绝对阈值」起步，自动沉淀本 Phase 不做**：自动沉淀踩 §6「自我弱化」红线（自身历史分当基准 = 自证）；起步用人工注册对照样本 + `QualityEvaluator` 三分达标线，先让门能真实拒绝。
4. **基线持久化 → 建议 `CORE_STATE_DIR` 单文件**：有先例（`MarketIndex`/`PendingQueue`/`_skill_state_path`，ADR-0103/0105）；「暂不落盘」= G4 只修一半，不可取；「随候选台账」职责不清。
5. **观察期口径 → 建议「同步，但最小侵入」**：门加「口径版本」字段，新口径只对新增候选生效，历史候选冻结在旧口径；SHALL NOT 一次性重算历史（避免「历史候选集体未过门」污染 `reuse_count`）。
6. **切片 → 建议「拆两次」**：先 G4+G3（数据面，做完即可构造「未过留出评测 ⇒ 拒绝」，分片验收 G5），后 G1+G2（判定面）。

**推荐决策组合**：

| # | 裁决点 | 建议 |
|---|---|---|
| 1 | G1–G5 定性 | 立账为能力缺口，按 Phase 落地 |
| 2 | 结晶面门 | 子集：pytest + ruff check，`GATE_COMMANDS` 派生 + spec 明文 |
| 3 | 基准集来源 | 人工注册 + 绝对阈值起步，自动沉淀暂缓 |
| 4 | 基线持久化 | `CORE_STATE_DIR` 单文件 |
| 5 | 观察期口径 | 同步，口径版本 + 历史冻结，不重算 |
| 6 | 切片 | 拆两次：G4+G3 → G1+G2 |

---

## 5. 去重边界

- **不重复 phase-27**：phase-27 修的是**实施面**（补丁落地的冻结门 + `EvolutionExecutor`）；本 Phase 修的是**结晶面**（候选发布的验证门 + 留出评测）。**两条门不同**，共用 `GATE_COMMANDS` 真源。
- **不重复 phase-21/24**：归因通道与内部核心插件接线已闭（ADR-0094/0095/0100），本 Phase 不动归因。
- **不重复 ADR-0100 的 E31 重开条件**：E31 是「13 内部模块未入 `PluginRegistry`」；本 Phase 是「门的产出恒为常量」。
- **不重复 phase-29**：编排调度/运行态，与本 Phase 无交集。
- **不重复 `skip_specs` 类先例**：本 Phase **非**规格中性（要改 `evolution` spec 三处 Requirement），**不得** `skip_specs`。

---

## 6. 红线（前置，实施时逐条守）

- **不得回退 `accepted` 诚实语义**：`_crystallize_plugin` 恒 `accepted`（「已批准、待人工实施」）SHALL NOT 因本 Phase 变为 `published`（ADR-0100 / spec `:266-268`）。
- **留出评测不得接进实施验证**：spec `:273-274` 明文；本 Phase 的真实 `Evaluator` 只服务**结晶面**。
- **门禁单一真源**：SHALL 取自 `GATE_COMMANDS`，SHALL NOT 另立第二份清单（spec `:273`）。
- **不谎称可逆**：新写路径若产生副作用，须 `EffectTracker.record(effect, undo)`；不产生就**照实写**（先例 ADR-0108 决策⑥）。
- **自我弱化防线**：验证门 SHALL **独立于被评产物**（phase-27 R1）；基准集 SHALL NOT 取自被评对象的自身历史分（否则自证）。
- **不得以缺陷修复名义 `skip_specs` 强推**（phase-27 同款红线）。

---

## 7. 下一步

- **✅ 已裁决（2026-10-06，用户）**：§4 六点按 §4.1 推荐组合落地 —— ① 立账为能力缺口 ② 结晶面门 =
  **子集**（`pytest` + `ruff check`，从 `GATE_COMMANDS` **派生**，spec 明文）③ 基准集来源 = 人工注册 +
  绝对阈值起步（不做自动沉淀）④ 基线持久化 = `CORE_STATE_DIR` 单文件 ⑤ 观察期口径 = 口径版本 + 历史
  冻结、不重算 ⑥ **拆两次**。
- **✅ 切片 1（G4+G3 数据面）已闭** —— change `0119` / **ADR-0112**：`BenchmarkRegistry` 落盘（跨进程
  可读、损坏降级告警）+ `BenchmarkScorer`（逐样本真实执行）+ `Evaluator` 三态（publish / rollback /
  **freeze**）+ 口径版本（`GATE_CALIBER`，候选台账盖章 + `crystallize` 校验）+ 结局词表 +1 `frozen`；
  组合根注入落盘 registry + 打分器。**G5 验收锚点实测**：**`frozen` 分支生产可达**（产线装配下
  `run_cycle` ⇒ `status="frozen"`）；**`rollback` 亦可达**（注册基准 + 基线 + 执行器时）。
- **✅ 切片 2（G1+G2 判定面）已闭** —— change `0120` / **ADR-0113**：真实 `review`
  （`build_review_prompt` / `parse_review` / `review_with`，模型面复用 `_llm_text` 接缝、判定 fail-closed）
  + 真实运行时测试（`crystallization_gates()` **按标记派生** + `run_gate_tests`，spec 明文写出结晶面跑
  `lint` + `test` 及为什么）+ **缺省 `Validator()` 不得放行** + `GATE_CALIBER` **1 → 2**。
  **G5 验收锚点实测**：`rejected` 生产可达。7 个既有测试文件**改判**（显式注入过门替身，读数器仍是真门）。
- **遗留给独立 change**：接入真实任务**执行器映射**（`runners`）使 `frozen` 不再恒真（ADR-0112 已知
  局限① 的 reopen 条件）；冷路径**异步化**（ADR-0113 已知局限① 的 reopen 条件）。
- 依赖：phase-27（`GATE_COMMANDS` / `SubprocessGateExecutor` / ADR-0105）+ phase-21/24（归因与结晶语义）。

---

## 8. 遗留清单（Phase 31 全闭时登记，2026-10-06）

> 本 Phase 的两个切片（`0119` 数据面 / `0120` 判定面）已闭；下列为**已知局限**，均**另有** reopen 条件，
> 不在本 Phase 范围内补做 —— 登记在此以免「门已名副其实」被读成「门已完美」。

| # | 遗留 | 性质 | reopen 条件 / 归属 |
|---|---|---|---|
| L1 | **产线未接基准执行器映射**（`runners` 空）⇒ 候选恒 `frozen` | 数据面完整、执行面**有意**留空（fail-closed 优先于「看得出在动」） | 接入真实任务执行器面并把 `runners` 注入组合根（ADR-0112 已知局限①） |
| L2 | **冷路径同步跑子进程门禁**（每轮维护节拍命中时 `pytest -q` ≈40s + 一次 review 调用） | 判定面在 `run_cycle` 的**唯一**落点（挪到操作面会让 `rejected` 仍不可达） | 冷路径**异步化**（ADR-0113 已知局限①） |
| L3 | **review 质量取决于模型与判定词表**（只认首行「通过词」起首） | **有意** fail-closed：宁可漏报不误放（模型先寒暄再 PASS ⇒ 判未过） | 需要否，另议；改词表即改判定口径 ⇒ **须递增 `GATE_CALIBER`** |
| L4 | 结晶面门禁是**仓库级**回归（与候选内容无关） | 技能级候选本无代码产物；候选**专属**产物的验证仍在**实施面**（冻结门） | 无（两门不同源、不互替，属设计而非缺陷） |
| L5 | 生产**未配模型** ⇒ 候选恒 `rejected` | **有意**：无审查判据即不得发布 | 组合根按既有约定注入模型调用（配置面） |
| L6 | 「未过门 ⇒ 教训写回 L2/L3」（spec 场景后半句）**未实现** | 既有形态（`run_cycle` 的 `rejected` 分支今日即不写记忆），本 Phase **不夹带** | 需要否，另议（ADR-0113 判据订正 (c)） |
