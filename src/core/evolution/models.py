"""进化引擎数据模型（evolution）。

承载四阶段闭环的数据流：Trace（行动→结果成对证据）→ DiagnosisReport →
GenerationCandidate → GateReport → EvalReport → EvolutionOutcome，以及评测基建
Benchmark / 三维质量报告 QualityReport。

对应接口：doc/03-interfaces/evolution-interface.md §2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

# 结晶面门的**口径版本**：判定所依据的 review / 运行时测试 / 留出评测口径的版本号。
# 任何改变结晶面判定口径的变更（新增判据、换打分生产者、换阈值语义）SHALL 递增它；递增即
# 「新口径只对新增候选生效」——旧候选随台账冻结在旧口径，投放时被拒（须按现口径重新提案），
# 历史结论 SHALL NOT 被重算（见 evolution spec「验证门」）。`0` = 口径字段引入之前（未知）。
# 版本轨迹：1 = 引入口径字段（判定面仍是恒通过桩）；2 = 判定面真实化（真实 review + 真实运行时
# 测试，change 0120 / ADR-0113）—— 旧口径候选即「按恒通过桩判定的候选」，不得投放。
GATE_CALIBER = 2


@dataclass
class Trace:
    """一条行动→结果成对证据（进化的唯一输入）。"""

    trace_id: str
    task_type: str
    action: dict[str, Any]
    result: Any
    success: bool
    metrics: dict[str, float] = field(default_factory=dict[str, float])
    plugin_id: str | None = None  # 归因线索：该 trace 关联的插件（可空）


@dataclass
class TraceRef:
    """对一条 trace 的轻量引用（DiagnosisReport.evidence 用）。"""

    trace_id: str
    ts: float = 0.0


@dataclass
class DiagnosisReport:
    """对比诊断报告：缺陷归因到单个插件（None 表示系统级）。"""

    target_plugin: str | None
    issue: str
    evidence: list[TraceRef] = field(default_factory=list[TraceRef])
    confidence: float = 0.0
    # 已沉淀的轮级失败摘要（change 0188 / ADR-0179）：归因**判定**不看它 —— 桥只增补证据面。
    # 缺省空 ⇒ 既有构造 / 相等 / 消费面（proposer 取 `issue`）逐字不变。
    failure_notes: list[str] = field(default_factory=list[str])


@dataclass
class GenerationCandidate:
    """世代化候选：不可变、带 delta 与 kind；status 承载「待人工确认」状态。"""

    generation: int
    target_plugin: str
    delta: dict[str, Any]
    kind: Literal["skill", "plugin"]
    # pending | confirmed | rejected | implemented（implemented = 制品已复核落地）
    status: str = "pending"  # 候选不得自动发布（低风险亦须显式 confirm）
    risk_level: Literal["low", "high"] = "low"  # 风险域：架构级(plugin)=high 必审；技能库级=low
    # 稳定身份：构造即固化、不依赖对象标识 —— 待确认队列跨进程可用（见 pending.py）
    candidate_id: str = field(default_factory=lambda: uuid4().hex[:12])
    # 提案时的结晶面门口径版本（随台账落盘）：与现口径不符者不得投放（见 GATE_CALIBER）
    caliber: int = GATE_CALIBER


@dataclass
class ImplementationRecord:
    """架构级候选的原生实施制品（`PendingItem` 的一个字段，与候选同生共死）。

    ``before`` 是**应用之前**的目标文件原内容（筹备一开始就随本记录落盘）：崩溃/异常发生在
    应用之后也不致把「被改过的内容」当成原内容。``gate`` 形如 ``{门名: {"passed": bool,
    "reason": str}}``（纯 dict，落盘零转换）。``gated`` 标记「门禁全过、可复核」，
    ``committed`` 标记「已复核落地」—— `commit` 只认前者为真者，落地后两者皆为真。
    """

    candidate_id: str
    path: str  # 仓内相对路径（与范围守卫校验的同一形态）
    before: str
    content: str
    gate: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    gated: bool = False
    committed: bool = False


@dataclass
class PatchProposal:
    """补丁生产者交出的单文件补丁：`path` 由**归因**解析得出，`content` 是**完整**文件内容。"""

    path: str
    content: str


@dataclass
class GateReport:
    """验证门报告：review + 运行时测试。"""

    passed: bool
    review: str
    test_results: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class EvalReport:
    """留出评测报告：防退化。"""

    passed: bool
    held_out_score: float
    baseline_score: float
    verdict: Literal["publish", "rollback", "freeze"]


@dataclass
class EvolutionOutcome:
    """一次进化闭环的最终产物。"""

    # published | accepted | pending | manual | rejected | rollback | frozen | no_evidence
    # | dissolved | implemented
    # accepted = 人工已批准、待人工实施（架构级候选：无自动产物落地）
    # implemented = 架构级候选的制品经人工复核后**已落地**（可选的原生执行器，见 executor.py）
    # frozen = 留出评测**无法评测**（无绑定基准 / 无样本 / 无执行器 / 无基线）⇒ 不下发、不发布：
    #   与 rollback（已判退化）语义分离，NOT 谎报为退化（见 evolution spec「留出评测」）
    status: str
    diagnosis: DiagnosisReport | None = None
    candidate: GenerationCandidate | None = None
    gate: GateReport | None = None
    eval: EvalReport | None = None
    skill_id: str | None = None


@dataclass
class Benchmark:
    """评测基准：输入样例 + 期望指标。

    ``plugin_id`` 是**候选↔基准的绑定**：留出评测按候选 `target_plugin` 选取基准，
    未绑定（``None``）的基准不参与任何候选的评测（SHALL NOT 回落「任意基准」，否则评测面
    与被评对象脱钩）。
    """

    benchmark_id: str
    task_type: str
    samples: list[dict[str, Any]]  # 每个 sample 含 input / expected
    metrics: dict[str, float] = field(default_factory=dict[str, float])
    plugin_id: str | None = None  # 绑定到该归因目标（候选 target_plugin）


@dataclass
class QualityReport:
    """三维任务质量评测：完成度 / 正确性 / 轨迹质量。"""

    completion: float
    correctness: float
    trajectory: float
