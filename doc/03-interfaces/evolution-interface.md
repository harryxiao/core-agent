# 接口设计：进化引擎接口（Evolution Interface）

> 层：L4 ｜ 对应规格 `evolution/spec.md` ｜ 模块 `02-modules/evolution.md`

---

## 1. 四阶段插件接口

```python
class Diagnoser(Plugin):
    plugin_id = "evolution.diagnoser"
    def diagnose(self, traces: list[Trace]) -> DiagnosisReport:
        """定位缺陷到单个插件级别。"""

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
    def validate(self, candidate: GenerationCandidate) -> GateReport:
        """review + 运行时测试，过验证门。"""

class Evaluator(Plugin):
    plugin_id = "evolution.evaluator"
    def evaluate(self, candidate: GenerationCandidate) -> EvalReport:
        """留出集评测，防过拟合/防退化。"""
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

@dataclass
class EvolutionGoal:
    plugin_id: str              # 本轮迭代目标（插件 id）
    score: float                # 喂给诊断的**先验权重**（按议程位次几何递减，恒 < 1.0）
    reason: str                 # 依据（失败数 / 已处理标记）—— 排序可解释
    directive: bool = False     # 显式目标（人指定）：直接采用、不参与归因竞争

@dataclass
class GateReport:
    passed: bool
    review: str
    test_results: dict

@dataclass
class EvalReport:
    passed: bool                # 留出集是否退化
    held_out_score: float
    baseline_score: float
    verdict: Literal["publish", "rollback", "freeze"]
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

class PendingQueue:
    def __init__(self, *, path: Path | None = None) -> None:
        """``path`` 注入则整体落盘（候选 + 门禁 + 评测）并在启动时恢复；缺省纯内存。"""
    def record(self, candidate, gate=None, eval=None) -> None:
        """登记一条候选（同 id 覆盖：门禁先行、评测补充）并落盘。"""
    def flush(self) -> None:                          # 候选状态变更后重写
    def records(self) -> list[PendingItem]: ...       # 台账快照（含已确认/已拒绝痕迹）
    def pending(self) -> list[GenerationCandidate]:   # 只含 status == "pending"
    def find(self, candidate_id: str) -> GenerationCandidate | None: ...
    def gate_of(self, candidate_id: str) -> GateReport | None: ...
    def eval_of(self, candidate_id: str) -> EvalReport | None: ...

# EvolutionEngine 增量
def pending(self) -> list[GenerationCandidate]: ...   # 待确认快照（status == "pending"）
def find(self, candidate_id: str) -> GenerationCandidate | None: ...
def reject(self, candidate: GenerationCandidate, *, reason: str | None = None) -> None:
    """人工拒绝：置 rejected + 落盘（可留 L2 教训）；被拒候选 crystallize 抛 CANDIDATE_PENDING。"""
```

| 维度 | 口径 |
|---|---|
| **稳定身份** | `GenerationCandidate.candidate_id`（UUID 前 12 位，**构造即固化**）——`Proposer._generation` 是进程内自增，跨进程不唯一，**不可作键**；门禁/评测检索一律按它 |
| **结论随候选** | 门禁与评测报告与候选**同一条记录**落盘：不留「候选在而结论缺」的半状态（否则重启后 `crystallize` 误判 `GATE_REJECTED` / `EVAL_REGRESSED`） |
| **待确认子集** | `pending()` 只列 `status == "pending"`；`confirm`/`reject` 后即出队，记录留在台账充当最小审计痕迹 |
| **拒绝语义** | `reject` 置 `rejected` 并落盘；被拒候选 `crystallize` 抛 `CANDIDATE_PENDING` |
| **持久化** | 组合根注入 `$CORE_STATE_DIR/evolution-pending.json`；缺省纯内存（零行为变化）；落盘缺失/损坏降级为**空台账**（不抛、不阻断启动） |

操作面（CLI，`core-agent evolve`）：

| 命令 | 语义 |
|---|---|
| `evolve pending` | 列出待确认候选（id / 风险域 / 目标 / 问题摘要）；空则打印「待确认队列为空」 |
| `evolve confirm <id>` | 确认并**立即结晶**（两步在一次动作内）；`risk_level="high"` 时**本命令即审批签发端**：构造 `ApprovalRequest(op="evolution.publish", target=候选目标, ...)` → `ApprovalWorkflow.approve()` → 携带获批单调 `confirm`。**结局文案按分支诚实**（change `0102`）：技能级 ⇒「已确认并发布：published」；架构级 ⇒「已批准（待人工实施）」（**不说「已发布」**） |
| `evolve reject <id> [--note TEXT]` | 拒绝候选（不再发布，可附理由） |

- **非待确认态不得复活**：`confirm`/`reject` 对不存在或非 `pending` 的候选一律给出反馈 + 非零退出。
- **签发端在操作面、判定仍在引擎**：操作面即「人工」这一事实的来源；引擎只收单据做判定（`confirm` 三重门语义一字不动）。
- **架构级结晶结局 = `accepted`**（change `0102`）：`confirm` 的**人工门一步不放宽**（`risk_level="high"`
  仍必须携带获批单），变的是**结晶结局的诚实性** —— 无产物落地就不报 `published`。
- **驱动面不变**：`evolve run` 仍是「跑一轮」（§4.1），跑出 `pending` 时提示候选 id。

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
| 门控（change `0067`） | `features.evolution: false` ⇒ 组合根**不建**引擎/worker，`DefaultLoop(cold_path=None)` —— 冷路径连同其唯一消费者一起消失（不是「装配了但不做事」）；`evolve` 四子命令同时拒绝 | 门控关闭时 `Runtime.evolution` 为空，`Runtime.loop._cold_path` 为 `None` |
| CLI `core-agent evolve run [--goal ID]` | 装配 runtime → `maybe_run(force=True, goal=…)` → 打印结局（指定 `--goal` 时先回显「本轮目标」） | **一次性动作**，不启常驻进程、不改运行态；装配失败 → stderr + 退出码 1 |

- **阈值门不搬进驱动面**：节奏语义（累计 trace 数）仍归 `EvolutionTrigger`，两处阈值必然漂移。
- **分层**：loop 属 L3、evolution 属 L4 → loop 只持 `Callable[[], None]`（冷路径）与
  `Callable[[str], None]`（trace 完成登记），装配由 `runtime.py` 做。
- **模块归因采集（change `0101`）**：`_to_traces` 除既有 `tool_call` 通道外，增**模块归因通道**
  —— 带 `module_id` 的事件（如 `loop.default` 自身失败）适配为
  `Trace(plugin_id=module_id, task_type="module_health", success=not payload["failed"])`，
  使架构模块自身失败成为可诊断证据；`plugin_id` 语义为**归因对象 id**（工具 id 或内部核心模块 id）。

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
| `EVAL_REGRESSED` | 留出集退化（触发回滚） |
| `CONFIRM_REQUIRED` | 架构级候选未获人工审批（无审批单 / 未批准 / 目标不符） |

`EvolutionOutcome.status` 取值：`published` / `accepted` / `pending` / `manual` / `rejected` / `rollback` / `no_evidence` / `dissolved`（观察期自动溶解）。

- `published` = **有产物落地**（技能级候选已写入技能库）。
- `accepted` = **人工已批准、待人工实施**（架构级候选：本仓无「自动生成并装配新一代 `Plugin` 对象」
  的生产者，故批准只作**登记**，不产出任何发布物；**不谎报 `published`**）——change `0102`。
  两种结局**观察期开窗一致**（判「批准/发布之后是否回归」，与是否有产物无关）。

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
