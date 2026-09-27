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
```

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
