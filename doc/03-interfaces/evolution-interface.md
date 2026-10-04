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
    def propose(self, diagnosis: DiagnosisReport) -> GenerationCandidate:
        """生成世代化产物（技能/插件补丁 + delta）。"""

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

    def run_cycle(self, traces: list[Trace]) -> EvolutionOutcome:
        d = self.diagnoser.diagnose(traces)
        if not d.target_plugin: return EvolutionOutcome(status="manual")
        c = self.proposer.propose(d)
        g = self.validator.validate(c)
        if not g.passed: return EvolutionOutcome(status="rejected", diagnosis=d)
        e = self.evaluator.evaluate(c)
        if e.verdict != "publish": return EvolutionOutcome(status="rollback", eval=e)
        return self.crystallize(c)          # 过门 → 结晶（经 MemoryStore + Registry）

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
    def open(self, target: str, *, baseline: float) -> ObservationWindow: ...
    def sample(self, target: str, score: float, *, now: float | None = None) -> bool:
        """记样本，返回是否触发回归（未开窗 / 冻结期内 → 忽略并返回 False）。"""
    def freeze(self, target: str, *, now: float | None = None) -> None: ...
    def window(self, target: str) -> ObservationWindow | None: ...

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
| **不调度** | `observe` 只是采样接缝——采样节奏由调用方决定（worker 冷路径等）；`now` 可注入，判定离线可断言 |

---

## 4. 触发接口

```python
class EvolutionTrigger:
    def maybe_run(self, traces: list[Trace], *, force: bool = False) -> bool:
        """累计 N 轮或强制时触发；后台低优先级执行。"""
```

---

## 5. 错误码

| 错误码 | 含义 |
|---|---|
| `NO_EVIDENCE` | 无结果证据（采集强制模式下无成对证据） |
| `CANDIDATE_PENDING` | 候选未过人工确认（禁止自动发布） |
| `GATE_REJECTED` | 验证门拒绝（review / 运行时测试不过） |
| `EVAL_REGRESSED` | 留出集退化（触发回滚） |
| `CONFIRM_REQUIRED` | 架构级候选未获人工审批（无审批单 / 未批准 / 目标不符） |

`EvolutionOutcome.status` 取值：`published` / `pending` / `manual` / `rejected` / `rollback` / `no_evidence` / `dissolved`（观察期自动溶解）。

---

## 6. 约束

- 进化**只读**观测 L3，不直接改运行态；产物必经 gate 才发布。
- 候选未过门 → 丢弃 + 教训写 L2/L3。
- 留出集退化 → 自动回滚 + 冻结冷却期。

---

## 7. 关联

- 模块：`02-modules/evolution.md`
- 记忆结晶：`memory-interface.md`
- 规格：`openspec/specs/evolution/spec.md`
