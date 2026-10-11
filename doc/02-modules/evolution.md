# 模块设计：进化引擎（L4 Evolution Engine）

> 对应规格：`doc/openspec/specs/evolution/spec.md` ｜ 接口：`doc/03-interfaces/evolution-interface.md`

---

## 1. 模块定位

L4 让 CORE **会进化**。它只读地观测 L3 循环的运行轨迹，通过
**诊断 → 提案 → 验证 → 评测** 四阶段闭环，把"经验"结晶为技能/插件，或在退化时溶解回退。

> **进化即结晶**：进化不是重写代码，而是把被反复验证有效的经验，沿着
> `经验(L4) → 技能(L3) → 插件(L0/L1)` 光谱向上结晶；失败则向下溶解。

---

## 2. 四阶段闭环

```
观测(Observe) ─► 诊断(Diagnose) ─► 提案(Propose) ─► 验证(Validate) ─► 评测(Evaluate)
     ▲                                                                      │
     └──────────────────────── 结晶/溶解 反馈 ────────────────────────────────┘
```

| 阶段 | 插件 | 职责 | 产出 |
|---|---|---|---|
| **诊断 Diagnose** | Diagnoser | 从轨迹找重复模式、缺陷、失效点，**归因到单个插件**；**可用时**并入已沉淀的轮级失败摘要（change `0188`／ADR-0179：经**注入的**查询接缝取 `loop.failure.<trace_id>`，有界 + fail-open；**不**改归因判定） | 诊断报告（`failure_notes`） |
| **提案 Propose** | Proposer | 生成世代化产物（新技能/插件补丁 + delta） | 世代候选 |
| **验证 Validate** | Validator | review + 运行时测试，过验证门 | gate 报告 |
| **评测 Evaluate** | Evaluator | 留出集评测，防过拟合/防退化 | 评测报告 |

---

## 3. 关键设计

### 3.1 可归因诊断（对应 ModularRSI 的模块级归因）

- 每个插件有独立的质量信号：成功/失败计数、回滚次数、用户修正次数。
- 诊断把缺陷定位到**单个插件级别**（"问题出在 memory.retrieve 的相关性打分"），
  而不是"整个系统不行"——这是**可归因自进化**的前提。
- 诊断接受**可选的目标先验**（`diagnose(prior=…)`，change `0084`）：权重恒 < 1.0 ⇒ **证据恒优先**，
  先验的**唯一**效果是解并列（无先验时并列仍转人工）。

### 3.2 世代化产物（不可变、版本化）

- 每次通过验证门的产物是一个**世代（generation）**：不可变、带 delta、带验证/评测报告。
- 未过门的候选**不进入运行**；过门的可发布、可回滚（切换世代）。
- **风险域随候选固化**（`risk_level`：`plugin`=架构级 `high` / `skill`=技能库级 `low`）。
  架构级候选 `confirm` **强制人工审批**：#9 起 `confirm(candidate, *, approval=None)` 要求一张
  目标一致的**已批准**权限审批单（判定走 permission 域 `is_approved`），缺失/未批准/目标不符一律
  fail-closed（`CONFIRM_REQUIRED`）；技能库级仍须**显式**人工确认——**不存在低风险自动结晶**。

### 3.3 验证门（Validation Gate）

- review（候选**自身自洽性**的结构化审查）+ 运行时测试（结晶面门禁子集）。任何一项失败 → 候选丢弃
  （`rejected`，**不发布**）。**两个判据的生产者都由组合根注入**（change `0120`；此前是恒通过桩 ⇒
  门恒开、「不合格候选被挡在门外」这句承诺不成立）：
  - **review**：`build_review_prompt` 渲染 `kind` / `target_plugin` / `delta` 的自洽性判据面，
    模型调用经 `review_with(_llm_text)` 注入（照 `author.py`：evolution **不 import LLM 抽象**）。
    判定只认**首行以「通过词」起首**；空输出 / 词表外 / 调用失败 ⇒ **未通过**（fail-closed）。
  - **运行时测试**：门禁子集**按标记派生**自门禁命令**单一真源** `GATE_COMMANDS`
    （`crystallization_gates()`：取 `lint` + `test` —— 轻量静态门与行为回归门；`typecheck` / `build`
    属**交付面**判据、不进结晶面）。标记命中未注册门名 ⇒ 派生**失败**（`CiCdError`，fail-closed）；
    执行面复用 `SubprocessGateExecutor`，「跑不起来」与「跑失败」同归为该门未通过。
  - **缺省 `Validator()` ⇒ 不得放行**（未注入生产者 ⇒ `passed=False`，理由据实写明「未注入」）；
    review 未过时 **fail-fast**（不再跑子进程门禁）。结果面 `test_results` 的值**恒为 `bool`**
    （混入原因字符串会被 `all()` 读成真 ⇒ 失败读成通过）。
  - **门的面（诚实）**：结晶面跑的是**仓库级**基线回归（与候选**内容无关**，技能级候选本无代码产物）；
    候选**专属**产物的验证属**实施面**（`EvolutionExecutor` 冻结门），两门不同源、不互替。
- **口径版本**（`GATE_CALIBER`，change `0119`；**判定面真实化时递增 1 → 2**，change `0120`）：
  结晶面门的判定口径带版本号；候选在**提案时**被盖上当时的口径并**随台账落盘**
  （`GenerationCandidate.caliber`）。投放（`crystallize`）时口径与现口径**不符** ⇒ **拒绝**
  （`GATE_CALIBER_STALE`，须按现口径重新提案）；**不重判历史**（口径变更不重跑历史候选）、拒绝理由
  **不**表述为「未过门 / 退化」。落盘**缺该字段的旧行**解析为口径 `0` ⇒ 一律拒绝。

### 3.4 留出评测（Held-out Eval，防过拟合）

- 留出集与进化过程**不相交**，只用于验证泛化。
- 候选在留出集上**退化** → 自动回滚，不发布。
- 这是把"自进化"变成"可验证的进化"的关键安全阀。
- **留出分的生产者**（change `0119`）：留出分 SHALL 由**已注册基准集的样本**经**基准执行器**逐样本
  **真实执行**后聚合产出（`BenchmarkScorer` → `QualityEvaluator` 三维分均值）；系统**不**以常量、
  占位值或缺省分充当留出分。候选经其 `target_plugin` 与基准的**绑定关系**（`Benchmark.plugin_id`）选取
  留出基准，**不**回落「任意基准」或「与被评对象同源」的基准。
- **三态判定**：`publish`（不退化）/ `rollback`（已判退化）/ **`freeze`（无法评测，fail-closed）**。
  候选无绑定基准 / 基准无样本 / 执行器未注册 / **未注册基线** ⇒ `freeze`（`status="frozen"`、
  `crystallize` 报 `EVAL_FROZEN`）：**不下发、不发布**，且 **SHALL NOT** 被谎报为「退化」。
- **阈值口径**：**已注册的基线分就是绝对阈值**（`held_out < baseline - margin` 即退化，`margin` 缺省
  `0.0`）；未注册基线**不**被静默当作 `0.0` 的宽松阈值放行。
- **数据面与执行面分离**：基准集与基线是**数据**（人工/运维注册、落 `$CORE_STATE_DIR` 单文件
  `evolution-benchmarks.json`、跨进程可读、损坏降级**告警**）；基准样本的**执行器**是**受信代码**
  （`task_type` → 可调用体），由**组合根或运维注入**、**不落盘**。基线 SHALL NOT 取自被评对象的
  自身历史分（自证）。

### 3.5 结晶与溶解

- **结晶 Crystallize**：L3 技能复用超阈值 → 提案为插件 → 过门后注册为代码。
- **溶解 Dissolve**：插件持续失败 → 卸载，语义+教训回写 L3（保留"为什么失败"）。
- 两者都经 L0 可逆效应，**永不丢历史**。
- **观察期自动溶解**（#10）：结晶**发布后即开窗**（基线 = 留出评测分）；调用方持续采样发布后的
  回归指标，样本数达下限（3）且均分低于「基线 − 容差」（0.2 绝对分差）→ **自动 `dissolve`**
  （技能标 `deprecated`、回归证据随教训写回 L2）；溶解后该方向**冻结一个冷却期**（期内不累积、
  不触发，避免溶解/重结晶抖动）。窗口仅进程内，采样节奏由调用方决定（引擎不内建调度）。

### 3.6 人工确认队列（跨进程可驱动，change `0055`）

- 过门候选**不自动发布**：候选连同其验证门报告与留出评测报告整体进 `PendingQueue`，
  由**人工**在操作面上确认后才 `crystallize` 发布。
- **稳定身份**：候选携带 `candidate_id`（构造即固化）——队列检索**不依赖对象标识**
  （`Proposer._generation` 是进程内自增、跨进程不唯一），故待确认事项可**跨进程**列出与处置。
- **落盘**：组合根注入 `$CORE_STATE_DIR/evolution-pending.json`（候选 + 门禁 + 评测**整体**快照，
  复用 `core/persistence.py` 的 JSON 原子写，零第三方依赖）；缺省纯内存（零行为变化）。
- **操作面**：CLI `core-agent evolve pending|confirm <id>|reject <id>`。`confirm` 一次动作完成
  「确认 + 发布」；`risk_level="high"` 时由操作面**签发**审批单（`ApprovalWorkflow.create → approve`）
  后再调 `confirm` —— 签发端在操作面（「人工」这一事实的来源），判定仍在引擎。
  非待确认态（不存在 / 已确认 / 已拒绝）一律反馈 + 非零退出，**不得复活**。

---

### 3.7 记忆面 → 诊断面桥（change `0188`／ADR-0179／账本 E125）

- **缺口**：轮级失败已沉淀为 L2 条目 `loop.failure.<trace_id>`（`loop` 写入侧，`failure_digest` 正文），
  但 `evolution` 对 memory **只写不读** ⇒ 诊断报告（进化闭环起点）**看不到**那份人类可读的失败叙述。
- **接法（依赖倒置）**：`Diagnoser.__init__` 收可选 `failure_lookup: Callable[[str], str \| None] | None`
  —— 与 `summarize_with(llm)` / `review_with(llm)` **同一接缝纪律**：单元**不** import 另一端能力包，
  由组合根（L5）注入具体实现（`runtime._failure_lookup(backend)`）。
- **并入面**：`DiagnosisReport.failure_notes: list[str]`（**新增可选字段**，缺省空 ⇒ 既有构造 / 相等 /
  消费面逐字不变）。**不改** `issue`（它是判定叙述，且被 `Proposer` 原样带进候选 `delta`）。
- **有界 + fail-open**：单条截断 400 字符、总数封顶 3 条（保留**先到**的失败证据）；查询抛错 ⇒ 吞掉、
  诊断照常。**归因判定（`target_plugin` / `confidence` / `evidence` / `issue`）逐字不变** —— 桥只增补证据面。
- **读取面零副作用**：组合根闭包走 `MemoryBackend.search("")`（**不**经 `MemoryStore.read`）⇒ 不强化
  `reuse_count`、不落盘（与 change `0187` 的「有副作用但有界」读取面**划清**）；按 **id 精确**取（同 trace
  的轨迹 / 步序条目 `source` 同为 `"loop"`）；**层无关** ⇒ 迁 L4 后仍可读。

### 3.8 结晶通路：执行面接线 + 基准注册面（change `0212`／ADR-0202／台账 E149）

- **缺口**：`0119` 的「数据面 / 执行面分离」只交付了**数据面**（`BenchmarkRegistry` 落盘）与
  `BenchmarkScorer(benchmarks, runners=...)` 的**接收**面 —— `runners` 由组合根注入、不落盘，而组合根
  **未传**、也**无**生产注册面 ⇒ 恒 `freeze` ⇒ `crystallize` 抛 `EVAL_FROZEN` ⇒ 「技能→插件」不可达。
- **执行面注入**：`BenchmarkScorer(benchmarks, runners=runners)`，`runners = {"module_health": _bench_runner,
  "tool_use": _bench_runner}`（worker 只产这两个 `task_type`）。runner 挂 **`general` 兜底子 profile**
  （非主 loop —— 主 loop 会经 `_cold_path` **递归**）；会话隔离 `session_id="bench"`；失败 ⇒ `None`、
  异常**冒泡**（精确匹配 scorer 语义）。
- **门控极性 = OPT_IN（缺省关，`features.evolution_benchmark_runner`）**：判据「**注册基准 ≠ 同意执行**」
  —— 跑基准烧模型 token ⇒ 执行面须**单独**显式开。旗关 ⇒ `runners=None` ⇒ 今日 `freeze` 判定逐字不变。
- **注册操作面**：CLI `core-agent evolve benchmark {register|set-baseline|list}` —— **数据面免 runtime**
  （`BenchmarkRegistry(path=...)`）。`register <id> --plugin-id <id> --task-type {module_health,tool_use}
  --samples <path.json>`（`--plugin-id` **必填**：绑定目标才激活评测）；`expected` 须与期望回复**逐字相等**。

## 4. 触发时机（异步、低优先级）

- 累计 N 轮轨迹后批量触发；或在连续失败/用户明确要求时触发。
- 进化是**后台冷路径**，绝不阻塞主循环热路径。
- **目标选择层（自动课程，change `0084` / 账本 E5）**：每一轮先由 `CurriculumPlanner` 定目标——
  失败强度定序、已处理目标（观察期中 / 已有待确认候选）降权、位次给先验权重（恒 < 1.0）。
  信号面**只含引擎内部结构化数据**：不读记忆自由文本、不调模型（排序须可解释、可断言）。
- **显式目标入口**：`core-agent evolve run --goal <plugin_id>` —— 人直接指定本轮迭代谁
  （`directive` 直接采用、不被证据改写），仍走完整四阶段与验证门。这是「迭代某个模块」的**可靠**
  入口；自动课程做**建议**，人做**指令**。

---

## 5. 错误处理与边界

| 场景 | 行为 |
|---|---|
| 诊断无法归因到单插件 | 扩大样本；仍无法归因则标记为"系统级"，人工介入 |
| 候选过不了验证门 | 丢弃，教训写 L2/L3 |
| 留出集退化 | 自动回滚，冻结该方向（冷却期） |
| 架构级候选未获审批 | `CONFIRM_REQUIRED`，候选保持 `pending`，不结晶（fail-closed） |
| 回滚失败 | QUARANTINE + 人工介入 |

---

## 6. 关联

- 队列实现：`src/core/evolution/pending.py`
- 目标选择层：`src/core/evolution/curriculum.py`
- 规格：`doc/openspec/specs/evolution/spec.md`
- 记忆结晶：`doc/02-modules/memory.md`
- 接口：`doc/03-interfaces/evolution-interface.md`
- 测试：`doc/04-testing/test-cases.md`（EVO 系列）
