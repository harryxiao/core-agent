# 接口设计：进化引擎接口（Evolution Interface）

> 层：L4 ｜ 对应规格 `evolution/spec.md` ｜ 模块 `02-modules/evolution.md`

---

## 1. 四阶段插件接口

```python
class Diagnoser(Plugin):
    plugin_id = "evolution.diagnoser"
    def __init__(
        self,
        plugin_signals: dict[str, float] | None = None,
        failure_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        """``failure_lookup``：**可选**的失败摘要查询接缝（change `0188`／ADR-0179，
        **依赖倒置**注入 —— 本单元不 import memory）。缺省 ``None``（未接线）⇒ 报告
        ``failure_notes`` 恒空、诊断与既往**逐字一致**；查询抛错 ⇒ 降级（该 trace 无摘要），
        归因判定不受牵连。"""
    def diagnose(self, traces: list[Trace]) -> DiagnosisReport:
        """定位缺陷到单个插件级别；**可用时**把已沉淀的轮级失败摘要
        （``loop.failure.<trace_id>``）并入 ``DiagnosisReport.failure_notes``
        （**有界**：单条 400 字符截断、总数封顶 3 条）。**归因判定**
        （``target_plugin`` / ``confidence`` / ``evidence`` / ``issue``）**逐字不变** ——
        桥只增补证据面（change `0188`／ADR-0179）。"""

class Proposer(Plugin):
    plugin_id = "evolution.proposer"
    def __init__(self, *, kind: Literal["skill", "plugin"] | None = None) -> None:
        """``kind`` 是**显式覆盖**：``None``（缺省）⇒ 按诊断归因判定。"""
    def propose(self, diagnosis: DiagnosisReport) -> GenerationCandidate:
        """生成世代化产物（技能/插件补丁 + delta）。

        `kind` 由**归因驱动**（change `0102`）：`diagnosis.target_plugin` 命中
        内部核心模块归因白名单 `INTERNAL_PLUGIN_IDS` ⇒ `plugin`/`high`（架构级，
        强制人工审批）；否则 ⇒ `skill`/`low`（技能库级）。显式 `kind` 恒优先。"""

class Validator(Plugin):
    plugin_id = "evolution.validator"
    def __init__(
        self,
        *,
        review: Callable[[GenerationCandidate], bool] | None = None,          # 未注入 ⇒ 不得放行
        tests: Callable[[GenerationCandidate], dict[str, bool]] | None = None,  # 同上；值恒 bool
    ) -> None: ...
    def validate(self, candidate: GenerationCandidate) -> GateReport:
        """review + 运行时测试，过验证门（change `0120` 起两个判据都由**组合根注入**）。

        **缺省 `Validator()` ⇒ 不得放行**（fail-closed，与 `Evaluator()` 的 `freeze` 同型）：
        未注入生产者 / review 输出不可解析 / 调用失败 / 门禁跑不起来 ⇒ `passed=False`。
        review 未过时 **fail-fast**（不再跑子进程门禁）。"""

# review 的生产者（evolution 域内、**不 import LLM 抽象**；模型调用由组合根给，先例 author.py）
def build_review_prompt(candidate: GenerationCandidate) -> str:
    """渲染候选**自洽性**判据面（kind / target_plugin / delta）+ 判定词表说明。"""
def parse_review(text: str) -> bool:
    """解析审查判定：只认**首行**以「通过词」（PASS / 通过）起首；词表外一律不通过。"""
def review_with(llm: Callable[[str], str]) -> Callable[[GenerationCandidate], bool]:
    """把「prompt → 文本」的模型调用适配为审查者契约（调用抛异常 ⇒ 不通过、不外抛）。"""

# 运行时测试的生产者（门禁子集**按标记派生**自单一真源，执行面复用 ci-cd 的 SubprocessGateExecutor）
def run_gate_tests(
    *, run_gate: Callable[[str], GateOutcome], gates: Sequence[str]
) -> Callable[[GenerationCandidate], dict[str, bool]]:
    """按门名逐道执行 ⇒ 门名 → bool（跑不起来 / 跑失败同归为 False，不外抛）。"""

# 门禁子集（ci-cd 域，change `0120`）：标记只标**门名**，命令字符串仍只有 GATE_COMMANDS 一份
CRYSTALLIZATION_GATE_MARKS: dict[str, str]  # {"lint": …, "test": …}（门名 → 可读理由）
def crystallization_gates() -> tuple[str, ...]:
    """派生结晶面门禁子集（顺序随单一真源）；标记命中未注册门名 ⇒ CiCdError(GATE_FAILED)。"""

class Evaluator(Plugin):
    plugin_id = "evolution.evaluator"
    def __init__(
        self,
        *,
        registry: BenchmarkRegistry | None = None,
        quality: QualityEvaluator | None = None,
        score_fn: Callable[[GenerationCandidate], float | None] | None = None,  # None = 无法评测
        max_concurrency: int = 4,
        margin: float = 0.0,        # 缺省 0.0 = 分毫不许退；阈值面是已注册基线（见下）
    ) -> None: ...
    def evaluate(self, candidate: GenerationCandidate) -> EvalReport:
        """留出集评测，防过拟合/防退化（三态：publish / rollback / **freeze**）。

        未注册基线（`registry.baseline_of` 返 `None`）或留出分不可得（`score_fn` 返 `None`）
        ⇒ `freeze`（**无法评测**，fail-closed）—— 不报 publish、不谎报 rollback。"""

class BenchmarkRegistry:
    """基准集 + 基线（``path`` 非空 ⇒ 单文件 JSON 落盘、跨进程可读；损坏降级 + 告警）。"""
    def __init__(self, *, path: Path | None = None) -> None: ...
    def register(self, benchmark: Benchmark) -> None: ...
    def benchmark_for_plugin(self, plugin_id: str) -> Benchmark | None: ...  # 绑定选取，无 ⇒ None
    def set_baseline(self, plugin_id: str, score: float) -> None: ...
    def baseline_of(self, plugin_id: str) -> float | None: ...   # 未注册 ⇒ None（判定面用）
    def baseline_score(self, plugin_id: str) -> float: ...        # 未注册 ⇒ 0.0（旧读面，非阈值）
    def list(self) -> list[Benchmark]: ...

class BenchmarkScorer:
    """基准执行器面：逐样本**真实执行** → 与期望对比 → 聚合成留出分。

    ``runners``（``task_type`` → 可调用体）由**组合根或运维注入**，**不随数据面落盘**
    （数据面可人工注册、执行面必须由受信代码提供）。执行器收到一个样本、返回实际结果；
    **无法评测**（无绑定基准 / 无样本 / 无该 `task_type` 的执行器）⇒ 返 `None`；
    执行器抛异常 ⇒ **冒泡**（不吞成 0 分、不吞成通过）。"""
```

---

## 2. 核心数据结构

```python
@dataclass
class DiagnosisReport:
    target_plugin: str | None   # 归因到的插件；None 表示系统级
    issue: str
    evidence: list[TraceRef]
    confidence: float
    failure_notes: list[str] = []   # 已沉淀的轮级失败摘要（change 0188；缺省空 ⇒ 逐字兼容）

@dataclass
class GenerationCandidate:
    generation: int
    target_plugin: str
    delta: dict                 # 变更内容（补丁/新技能）
    kind: Literal["skill", "plugin"]
    status: str = "pending"     # 候选状态：pending → confirmed（待人工确认，不自动发布）
    risk_level: Literal["low", "high"] = "low"
    # 风险域（提案阶段按 kind 固化）：plugin → high（架构级，强制人工审批）；
    # skill → low（技能库级，仍须显式 confirm，只是不要求权限工单）
    caliber: int = GATE_CALIBER  # 提案时的结晶面门口径版本（随台账落盘；用途见 §5.1）

@dataclass
class EvolutionGoal:
    plugin_id: str              # 本轮迭代目标（插件 id）
    score: float                # 喂给诊断的**先验权重**（按议程位次几何递减，恒 < 1.0）
    reason: str                 # 依据（失败数 / 已处理标记）—— 排序可解释
    directive: bool = False     # 显式目标（人指定）：直接采用、不参与归因竞争

@dataclass
class GateReport:
    passed: bool
    review: str                 # 门未过时的据实理由（未注入生产者 / 拒绝 / …）
    test_results: dict          # 门名 → bool（值恒 bool：混入原因字符串会被 all() 读成真）
    # 结晶面门是**仓库级**回归门（GATE_COMMANDS 子集），与候选内容无关；候选专属产物的验证
    # 属**实施面**（EvolutionExecutor 冻结门）—— 两门不同源、不互替

@dataclass
class EvalReport:
    passed: bool                # 留出集是否退化
    held_out_score: float       # freeze 时记 0.0 且**无意义**（消费者只认 verdict）
    baseline_score: float
    verdict: Literal["publish", "rollback", "freeze"]
    # freeze = 无法评测（无绑定基准 / 无样本 / 无执行器 / 无基线）⇒ fail-closed，非「退化」

@dataclass
class Benchmark:
    benchmark_id: str
    task_type: str              # 选取执行器的键（runners[task_type]）
    samples: list[dict]         # 每个 sample 含 input / expected
    metrics: dict[str, float] = {}
    plugin_id: str | None = None  # 绑定到候选 target_plugin（不绑定者不参与任何评测）
```

---

## 3. 编排器（Evolution Engine）

```python
class EvolutionEngine(Plugin):
    plugin_id = "evolution.engine"

    def run_cycle(self, traces: list[Trace], *,
                  goals: Sequence[EvolutionGoal] | None = None) -> EvolutionOutcome:
        # goals = 课程议程：directive 直接采用；其余作诊断**先验**（只破并列，不压证据）
        d = self.diagnoser.diagnose(traces)
        if not d.target_plugin: return EvolutionOutcome(status="manual")
        c = self.proposer.propose(d)
        g = self.validator.validate(c)
        if not g.passed: return EvolutionOutcome(status="rejected", diagnosis=d)
        e = self.evaluator.evaluate(c)
        if e.verdict != "publish": return EvolutionOutcome(status="rollback", eval=e)
        # 过门候选进**人工确认队列**（不自动发布）——见 §3.2
        return EvolutionOutcome(status="pending", candidate=c, gate=g, eval=e)

    def confirm(self, candidate: GenerationCandidate, *,
                approval: ApprovalTicket | None = None) -> None:
        """人工确认候选（放行发布）；risk_level="high" 须携带目标一致的已批准审批单。"""
```

| 维度 | 口径 |
|---|---|
| **门禁** | `risk_level="high"`（`kind="plugin"`）→ 三重校验：**有单 + 已批准 + `request.target` 与候选一致**；任一不满足抛 `CONFIRM_REQUIRED`（fail-closed，候选保持 `pending`） |
| **判定** | 审批判定走 permission 域的 `is_approved(ticket)`（状态词表不泄漏到本域） |
| **低风险** | `risk_level="low"` 忽略 `approval`，行为同今天——**仍须显式 confirm**（不引入低风险自动结晶） |
| **可追溯** | 审批单携带 `target` / `trace_id` 并经 `ApprovalWorkflow` 归档（`list_archived`），不新增候选字段 |

### 3.1 观察期回归自动溶解（auto-dissolve）

```python
@dataclass
class ObservationWindow:
    target: str                 # 观察目标（= 候选 target_plugin，与 dissolve() 同键）
    baseline: float             # 结晶发布时的评测基线分
    samples: list[float]        # 发布后的实测分（冻结时清零）
    frozen_until: float         # 冻结冷却期截止
    @property
    def mean(self) -> float     # 观察均分（无样本 → 0.0）

class ObservationRegistry:
    def __init__(self, *, path: Path | None = None, ...) -> None:
        """``path`` 注入则落盘（基线 / 样本 / 冻结截止），启动恢复；缺省纯内存。"""
    def open(self, target: str, *, baseline: float) -> ObservationWindow: ...
    def sample(self, target: str, score: float, *, now: float | None = None) -> bool:
        """记样本，返回是否触发回归（未开窗 / 冻结期内 → 忽略并返回 False）。"""
    def freeze(self, target: str, *, now: float | None = None) -> None: ...
    def window(self, target: str) -> ObservationWindow | None: ...
    def targets(self) -> list[str]: ...   # 已开窗目标（供采样侧按目标归因上报）

# EvolutionEngine
def observe(self, target: str, score: float, *, now: float | None = None) -> EvolutionOutcome | None:
    """观察期采样；回归超阈值 → 自动 dissolve + 冻结（返回 status="dissolved"，否则 None）。"""
```

| 维度 | 口径 |
|---|---|
| **开窗** | `crystallize` **发布成功后**开窗（基线 = 该候选 `eval.held_out_score`）；未开窗目标的采样被忽略（不建窗、不抛异常） |
| **回归判据** | 样本数 ≥ `_OBSERVE_MIN_SAMPLES`(3) **且** 均分 < 基线 − `_REGRESSION_TOLERANCE`(0.2，绝对分差，与 `Evaluator.margin` 同形状) |
| **冻结** | 溶解即冻结该目标 `_FREEZE_COOLDOWN_S`(300s) 并**清零样本**；冷却期内不累积、不触发，到期自动恢复采样 |
| **留痕** | 回归证据（基线 / 观察均分 / 样本数）拼进 `dissolve` 的教训条目（L2，`tags` 含 `dissolve`） |
| **采样来源** | 生产侧由 `EvolutionWorker._sample_observations` 供数：每轮 `run_cycle` 后对本批 trace 中**已开窗**目标按 `plugin_id` 归因算批次成功率并各上报一次；无归因 trace 的目标不采样（线上代理指标，与留出评测分近似可比） |
| **持久化** | 注入 `path` 则窗口（含**冻结截止**）落盘、启动恢复——冻结期跨进程仍有效；缺省纯内存（零行为变化） |
| **不调度** | `observe` 只是采样接缝——采样节奏由调用方决定（worker 冷路径）；`now` 可注入，判定离线可断言 |
| **重发布即重开窗** | 同一 `target` 再次 `open` **覆盖**旧窗口（基线重置、旧样本丢弃）——这是**有意语义**（账本 A6 按此关闭）：该窗口判的是「**当前那次发布**是否回归」，跨版本样本混池会让基线失义。多次发布/回滚的**历史**留痕不在本接缝内；需要审计时由 `dissolve` 教训条目（L2）与遥测流承载 |

### 3.2 人工确认队列与操作面（change `0055`）

```python
@dataclass
class PendingItem:                       # 一条候选记录：候选 + 门禁/评测结论（同生共死）
    candidate: GenerationCandidate
    gate: GateReport | None = None
    eval: EvalReport | None = None       # 参数名对齐领域词表（遮蔽内建 eval）
    implementation: ImplementationRecord | None = None   # 原生实施制品（change `0112`）

class PendingQueue:
    def __init__(self, *, path: Path | None = None) -> None:
        """``path`` 注入则整体落盘（候选 + 门禁 + 评测 + 实施制品）并在启动时恢复；缺省纯内存。"""
    def record(self, candidate, gate=None, eval=None) -> None:
        """登记一条候选（同 id 覆盖：门禁先行、评测补充）并落盘；**保留**既有制品不静默抹掉。"""
    def flush(self) -> None:                          # 候选状态变更后重写
    def records(self) -> list[PendingItem]: ...       # 台账快照（含已确认/已拒绝痕迹）
    def pending(self) -> list[GenerationCandidate]:   # 只含 status == "pending"
    def find(self, candidate_id: str) -> GenerationCandidate | None: ...
    def gate_of(self, candidate_id: str) -> GateReport | None: ...
    def eval_of(self, candidate_id: str) -> EvalReport | None: ...
    def implementation_of(self, candidate_id: str) -> ImplementationRecord | None: ...
    def attach_implementation(self, record: ImplementationRecord) -> bool:
        """挂制品到**既有**候选记录；候选不在台账 ⇒ 返回 ``False``（不静默造条目）。"""
    def clear_implementation(self, candidate_id: str) -> None: ...
    def staged(self) -> list[ImplementationRecord]: ...   # 待复核（gated 且未 committed）

# EvolutionEngine 增量
def pending(self) -> list[GenerationCandidate]: ...   # 待确认快照（status == "pending"）
def find(self, candidate_id: str) -> GenerationCandidate | None: ...
def reject(self, candidate: GenerationCandidate, *, reason: str | None = None) -> None:
    """人工拒绝：置 rejected + 落盘（可留 L2 教训）；被拒候选 crystallize 抛 CANDIDATE_PENDING。"""
```

| 维度 | 口径 |
|---|---|
| **稳定身份** | `GenerationCandidate.candidate_id`（UUID 前 12 位，**构造即固化**）——`Proposer._generation` 是进程内自增，跨进程不唯一，**不可作键**；门禁/评测检索一律按它 |
| **结论随候选** | 门禁与评测报告、以及（可选）**原生实施制品**都与候选**同一条记录**落盘：不留「候选在而结论缺」的半状态（否则重启后 `crystallize` 误判 `GATE_REJECTED` / `EVAL_REGRESSED`） |
| **待确认子集** | `pending()` 只列 `status == "pending"`；`confirm`/`reject` 后即出队，记录留在台账充当最小审计痕迹 |
| **拒绝语义** | `reject` 置 `rejected` 并落盘；被拒候选 `crystallize` 抛 `CANDIDATE_PENDING` |
| **持久化** | 组合根注入 `$CORE_STATE_DIR/evolution-pending.json`；缺省纯内存（零行为变化）；落盘缺失/损坏降级为**空台账**（不抛、不阻断启动） |

操作面（CLI，`core-agent evolve`）：

| 命令 | 语义 |
|---|---|
| `evolve pending` | 列出待确认候选（id / 风险域 / 目标 / 问题摘要）；空则打印「待确认队列为空」 |
| `evolve confirm <id>` | 确认并**立即结晶**（两步在一次动作内）；`risk_level="high"` 时**本命令即审批签发端**：构造 `ApprovalRequest(op="evolution.publish", target=候选目标, ...)` → `ApprovalWorkflow.approve()` → 携带获批单调 `confirm`。**结局文案按分支诚实**（change `0102`）：技能级 ⇒「已确认并发布：published」；架构级 ⇒「已批准（待人工实施）」（**不说「已发布」**） |
| `evolve reject <id> [--note TEXT]` | 拒绝候选（不再发布，可附理由） |
| `evolve implement <id> [--dry-run] [--approver NAME] [--note TEXT]` | 架构级候选的**原生实施**（**可选能力**，见 §3.3）：`--dry-run` = **筹备**（产出补丁 → 跑冻结门 → **回退**）并打印待复核 diff；缺省 = 复核后**永久落地**（结局 `implemented`）。**未启用执行器** ⇒ stderr 说明 + **rc 0**（能力关闭不是错误，沿 `_module_disabled` 惯例） |

- **非待确认态不得复活**：`confirm`/`reject` 对不存在或非 `pending` 的候选一律给出反馈 + 非零退出。
- **签发端在操作面、判定仍在引擎**：操作面即「人工」这一事实的来源；引擎只收单据做判定（`confirm` 三重门语义一字不动）。
- **架构级结晶结局 = `accepted`**（change `0102`）：`confirm` 的**人工门一步不放宽**（`risk_level="high"`
  仍必须携带获批单），变的是**结晶结局的诚实性** —— 无产物落地就不报 `published`。
- **驱动面不变**：`evolve run` 仍是「跑一轮」（§4.1），跑出 `pending` 时提示候选 id。
- **原生实施是「第二阶段」，不是「第二个人工门」**（change `0112`）：`confirm` 批「**做什么**」、
  `implement` 的复核批「**改得对不对**」；复核单 `op="evolution.implement"`，与 `confirm` 的
  `evolution.publish` **不可互换**（跨阶段复用同一张单 ⇒ `CONFIRM_REQUIRED`）。

### 3.3 原生实施执行器（可选，change `0112`）

`accepted`（人工已批准、**待人工实施**）**不能**闭合架构总纲承诺的「验证通过 ⇒ 产出不可变世代」
（`core_harness_architecture.md:150-153/158`）—— 缺的是最后一跳：把「已批准」变成「已落地」。
`EvolutionExecutor` 补上这一跳，且**缺省不启用**（`features.evolution_executor`，fail-closed；
取舍见 ADR-0105）。

```python
@dataclass
class ImplementationRecord:              # 与候选同一条记录承载（PendingItem.implementation）
    candidate_id: str
    path: str                            # 仓内相对路径（与范围守卫校验的同一形态）
    before: str                          # **应用之前**的目标文件原内容（先落盘再应用 ⇒ 崩溃安全）
    content: str                         # 被复核的那一份补丁（完整文件内容）
    gate: dict[str, dict[str, Any]]      # {门名: {"passed": bool, "reason": str}}
    gated: bool = False                  # 门禁全过、可复核
    committed: bool = False              # 已复核落地

@dataclass
class PatchProposal:                     # 补丁生产者交出的单文件补丁
    path: str
    content: str

class EvolutionExecutor:
    def __init__(self, *, author: PatchAuthor, run_gate: Callable[[str], GateOutcome],
                 gates: tuple[str, ...], effects: EffectTracker,
                 queue: PendingQueue, root: Path) -> None: ...
    def prepare(self, candidate: GenerationCandidate) -> ImplementationRecord: ...
    def commit(self, candidate: GenerationCandidate, *,
               approval: Any | None = None) -> EvolutionOutcome: ...
    def staged(self, candidate_id: str) -> ImplementationRecord | None: ...
    def staged_all(self) -> list[ImplementationRecord]: ...
```

| 维度 | 口径 |
|---|---|
| **触发形态** | **操作面显式驱动**（`evolve implement`）：**不**挂 loop 热/冷路径节拍（同步跑四道门禁 = 阻塞热路径，且 `confirm` 是一次性进程 ⇒ 冷路径永不命中）、**不**注册为任何 Agent 工具（自改代码不经模型手）；两阶段、**复核前 SHALL NOT 落地** |
| **补丁来源** | 注入的补丁生产者；组合根以 `patch_author_with(llm, read_source)` 接地（照 `summarize_with` / `sop_writer_with` 惯用法），执行器只依赖 `PatchAuthor` Protocol |
| **归因一致** | 补丁路径 **SHALL** 由候选 `target_plugin`（须 ∈ `INTERNAL_PLUGIN_IDS`）经约定 `src/core/<点转斜杠>.py` 解析，且目标文件**必须存在** |
| **范围守卫** | 白名单形态：仅 `src/core/` 内的 `.py`，减去**信任集**（`ci_cd/**`、`permission/**`、`evolution/**`、`configuration/**`、`runtime.py`、`entry.py`、`persistence.py`）；另拒绝对路径 / `..` 段 / 非 `.py` |
| **门禁冻结** | 门名与命令取自**单一真源** `GATE_COMMANDS`（组合根注入，执行器**不自选**）；复用组合根既有 `gate_executor` |
| **可逆** | 应用与落地各记一条 `Effect`（`undo` 恢复写入前内容）；筹备的临时应用在 `finally` 里回退 ⇒ 工作树不留改动；效应按 trace 分组（`evolution.prepare.<cid>` / `evolution.commit.<cid>`） |
| **漂移拒绝** | 落地前校验目标文件当前内容与 `before` 一致 ⇒ 不符抛 `IMPLEMENT_STALE`（不把补丁盖到外部改动上）；筹备起点同样拒绝脏树 |
| **待复核判据** | 「待复核」≡ **门禁全过**（`gated=True`）且未落地：筹备中断（门禁抛错 / 进程被杀）留下的 `gated=False` 残留制品**不是**可复核对象 ⇒ 落地拒绝（`IMPLEMENT_REJECTED`）、`evolve pending` 不列出（留痕仍可经台账查得）—— change `0127` / E69 |
| **已知局限** | 本切片的冻结门是当时**唯一**真门（**已订正**：change `0119` 起 `Evaluator` 是真门、change `0120` 起 `Validator` 亦是真门 —— 见 §1；结晶面门跑的是**仓库级**回归，候选专属产物的验证仍只由本冻结门承担）；无物理隔离；`commit` 的 undo 无 CLI 回退入口；门禁副产物（`dist/`、`.pytest_cache`）不入回退（ADR-0105 照实登记） |


---

## 4. 触发接口

```python
class EvolutionTrigger:
    def maybe_run(self, traces: list[Trace], *, force: bool = False) -> bool:
        """累计 N 轮或强制时触发；后台低优先级执行。"""
```

### 4.1 冷路径驱动面（cold path driving，change `0051`）

`EvolutionWorker` 是冷路径的唯一消费者，但其 `on_trace_complete` / `maybe_run` **在生产必须有驱动面**
（否则 L4 整条冷路径离线）。系统提供两个驱动入口，二者都只调 `maybe_run`——**是否真正跑一轮由
`EvolutionTrigger` 阈值门决定**（显式入口以 `force` 跳过阈值门）：

```python
class EvolutionWorker:
    def maybe_run(self, *, force: bool = False,
                  goal: str | None = None) -> EvolutionOutcome | None:
        """阈值命中或强制时 replay 累积 trace → **课程定目标** → run_cycle，
        并按批次指标采样观察窗口；未达阈值返回 None。`goal` 为显式目标（直接采用）。"""
```

| 入口 | 形状 | 停止语义 |
|---|---|---|
| loop 收尾维护节拍 | 组合根把冷路径回调注入 `DefaultLoop(cold_path=...)`；与记忆维护**共用节拍闸门**（`maintenance_interval`），各自失败降级、不中断本轮 | 节拍只给**机会**，阈值门决定是否做事（未达阈值 `maybe_run()` 返回 `None`） |
| loop 收尾 trace 完成回调（change `0101`） | 组合根把 `EvolutionWorker.on_trace_complete` 注入 `DefaultLoop(trace_observer=...)`；**按轮、不节流**（与 `cold_path` 是两个独立节律），在本轮**全部遥测记录完毕后**提交 `trace_id`（只登记、不触发、不阻塞），失败降级留痕 | 只**登记**已完成 trace（追加 `_completed`），是否跑 cycle 仍由阈值门在下次冷路径机会决定 |
| 门控（change `0067`） | `features.evolution: false` ⇒ 组合根**不建**引擎/worker，`DefaultLoop(cold_path=None)` —— 冷路径连同其唯一消费者一起消失（不是「装配了但不做事」）；`evolve` 五子命令同时拒绝 | 门控关闭时 `Runtime.evolution` 为空，`Runtime.loop._cold_path` 为 `None` |
| 实施器门控（change `0112`） | `features.evolution_executor`（**缺省关**，`is_enabled` 判据，与上面**极性相反**）⇒ 组合根**不建** `EvolutionExecutor`；`evolve implement` 给出「能力已关闭」说明 + **rc 0** | 缺省 `Runtime.evolution_executor is None`；`features.evolution: false` 时实施器同样不存在（转出源码无处安放） |
| CLI `core-agent evolve run [--goal ID]` | 装配 runtime → `maybe_run(force=True, goal=…)` → 打印结局（指定 `--goal` 时先回显「本轮目标」） | **一次性动作**，不启常驻进程、不改运行态；装配失败 → stderr + 退出码 1 |

- **阈值门不搬进驱动面**：节奏语义（累计 trace 数）仍归 `EvolutionTrigger`，两处阈值必然漂移。
- **分层**：loop 属 L3、evolution 属 L4 → loop 只持 `Callable[[], None]`（冷路径）与
  `Callable[[str], None]`（trace 完成登记），装配由 `runtime.py` 做。
- **模块归因采集（change `0101`）**：`_to_traces` 除既有 `tool_call` 通道外，增**模块归因通道**
  —— 带 `module_id` 的事件（如 `loop.default` 自身失败）适配为
  `Trace(plugin_id=module_id, task_type="module_health", success=not payload["failed"])`，
  使架构模块自身失败成为可诊断证据；`plugin_id` 语义为**归因对象 id**（工具 id 或内部核心模块 id）。
- **两条通道的生产方（change `0107`）**：① `tool_call` 通道由**执行循环在生产链路产出**
  （`DefaultLoop` 非终止动作完成后经 `TraceLogger.log_tool_call`，见 observability 接口 §2）——
  此前只有消费侧就绪、无生产调用方（E30）；② 模块归因通道由 loop 自身失败留痕产出（如预算耗尽）。
- **`plugin_id` = 归因对象身份（change `0107` 钉死口径）**：它标识「进化引擎**监控谁**、缺陷
  **定位到谁**」，**SHALL NOT 蕴含**该 id 已纳入 `PluginRegistry` 生命周期。**裁决（E31）**：内部核心
  模块**不**纳入注册表、**不**补 `load`/`unload` 空转形态 —— 依据：注册表全仓仅 `PluginInstaller`
  内部默认构造、无消费方；14 个模块里仅 8 个具 Plugin 六件套且 `load`/`unload` 全 `return None`、
  `check()` 7/8 恒真（真检查仅 `evolution.engine` / `composition.resolver`）⇒ 补全后仍无信号、无行为
  （ADR-0094 决策①已否决）。**重开条件**：出现「真的会产出新一代 `Plugin` 对象」的生产者（模型生成 /
  人工提交补丁）—— 届时 `promote(plugin: Plugin)` 才有语义（ADR-0100）。

### 4.2 自动课程（目标选择层，change `0084` / 账本 E5）

闭环四阶段与两个驱动面都已接线，缺的是**「这一轮该迭代谁」**。`CurriculumPlanner` 补上这一层：
它只吃**引擎内部的结构化信号**，产出**有界、有序、确定**的议程，供 `run_cycle` 作诊断先验。

```python
class CurriculumPlanner:
    def __init__(self, *, observations: ObservationRegistry | None = None,
                 pending: Callable[[], Sequence[GenerationCandidate]] | None = None) -> None: ...

    def plan(self, traces: Iterable[Trace], *, explicit: str | None = None,
             limit: int = 3) -> list[EvolutionGoal]:
        """显式目标直采；否则按失败强度定序 → 已处理目标降权 → 位次给权重。"""
```

| 维度 | 口径 |
|---|---|
| **信号面（封闭）** | 只读结构化数据：① 本批失败计数（按 `plugin_id`）；② 观察期目标（已发布、观察中）；③ 待确认候选。**不读记忆自由文本、不调模型**（无结构化教训标记；模型排序非确定且不可验证） |
| **定序** | 失败强度降序 → 已处理目标（观察期中 / 已有待确认候选）排后 → `plugin_id` 升序兜底（**确定性**） |
| **权重** | 位次几何递减（首位 0.5，其后 0.25/0.125 …）——恒 < 1.0 ⇒ **证据恒优先、先验只破并列**；降权同理只改并列顺序 |
| **预算** | 议程长度 ≤ `limit`（默认 3）——P5「token 有界」在目标选择层的落地 |
| **显式目标** | `evolve run --goal X` ⇒ `directive=True` 的**唯一**目标：直接采用、不被证据改写，仍走完整四阶段 + 验证门 + 人工 `confirm` |
| **开课** | `EvolutionWorker` 缺省自建 planner（只读 `engine.observations` / `engine.pending` ⇒ 零额外接线）；可注入替换 |

- **不是第三个驱动面**：课程在引擎内，不常驻、不给模型新工具；驱动面仍只有 §4.1 的两个。
- **不放宽人工门**：课程只影响**提案给谁**，不影响**发布是否要人批**（低风险候选仍须显式 `confirm`）。

---

## 5. 错误码

| 错误码 | 含义 |
|---|---|
| `NO_EVIDENCE` | 无结果证据（采集强制模式下无成对证据） |
| `CANDIDATE_PENDING` | 候选未过人工确认（禁止自动发布） |
| `GATE_REJECTED` | 验证门拒绝（review / 运行时测试不过） |
| `EVAL_REGRESSED` | 候选未过留出评测（触发回滚） |
| `EVAL_FROZEN` | 候选**无法评测**（无绑定基准 / 无样本 / 无执行器 / 无基线）⇒ 不下发、不发布；**非**「退化」——change `0119` |
| `GATE_CALIBER_STALE` | 候选口径版本与现口径不符（旧口径候选不得投放，须按现口径重新提案）——change `0119` |
| `CONFIRM_REQUIRED` | 架构级候选未获人工审批（无审批单 / 未批准 / 目标不符）；原生实施的复核单缺失 / 未批准 / 目标不符 / `op` 非 `evolution.implement` 亦复用之 |
| `IMPLEMENT_REJECTED` | 原生实施前置不满足（候选非已确认的架构级 / 归因不在白名单 / 范围守卫拒绝 / 未筹备即落地 / **未过门的残留制品**（change `0127`）/ 筹备回退失败）——change `0112` |
| `IMPLEMENT_STALE` | 目标文件自筹备以来已被改动（落地前漂移校验失败）——change `0112` |

`EvolutionOutcome.status` 取值：`published` / `accepted` / `pending` / `manual` / `rejected` / `rollback` / `frozen`（无法评测，change `0119`）/ `no_evidence` / `dissolved`（观察期自动溶解）/ `implemented`（制品已复核落地，change `0112`）。

- `published` = **有产物落地**（技能级候选已写入技能库）。
- `accepted` = **人工已批准、待人工实施**（架构级候选：本仓无「自动生成并装配新一代 `Plugin` 对象」
  的生产者，故批准只作**登记**，不产出任何发布物；**不谎报 `published`**）——change `0102`。
  两种结局**观察期开窗一致**（判「批准/发布之后是否回归」，与是否有产物无关）。
- `implemented` = 架构级候选的**源文件补丁**经人工复核后**已永久落地**（`features.evolution_executor`
  开启时的第二阶段结局）。它与 `published` 的区别在**产物形态**：`published` 是 L3 技能库产物，
  `implemented` 是 `src/core/**` 源码补丁；`accepted` 的「未实施」诚实语义**不回退**为 `published`。
- `frozen` = 留出评测**无法评测**（无绑定基准 / 无样本 / 无执行器 / 无基线）⇒ **不下发、不发布**；
  与 `rollback`（**已判退化**）语义分离 —— 「无法评测」SHALL NOT 被谎报为「退化」——change `0119`。
  组合根**暂未接**执行器映射 ⇒ 生产装配下候选恒 `frozen`（见 ADR-0112 已知局限①）。

---

## 6. 约束

- 进化**只读**观测 L3，不直接改运行态；产物必经 gate 才发布。
- 候选未过门 → 丢弃 + 教训写 L2/L3。
- 留出集退化 → 自动回滚 + 冻结冷却期。

---

## 7. 关联

- 模块：`02-modules/evolution.md`
- 记忆结晶：`memory-interface.md`
- 队列实现：`src/core/evolution/pending.py`
- 目标选择层：`src/core/evolution/curriculum.py`
- 规格：`openspec/specs/evolution/spec.md`
