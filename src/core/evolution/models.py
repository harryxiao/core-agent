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


@dataclass
class GenerationCandidate:
    """世代化候选：不可变、带 delta 与 kind；status 承载「待人工确认」状态。"""

    generation: int
    target_plugin: str
    delta: dict[str, Any]
    kind: Literal["skill", "plugin"]
    status: str = "pending"  # pending | confirmed | rejected（候选不得自动发布）
    risk_level: Literal["low", "high"] = "low"  # 风险域：架构级(plugin)=high 必审；技能库级=low
    # 稳定身份：构造即固化、不依赖对象标识 —— 待确认队列跨进程可用（见 pending.py）
    candidate_id: str = field(default_factory=lambda: uuid4().hex[:12])


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

    # published | accepted | pending | manual | rejected | rollback | no_evidence | dissolved
    # accepted = 人工已批准、待人工实施（架构级候选：无自动产物落地）
    status: str
    diagnosis: DiagnosisReport | None = None
    candidate: GenerationCandidate | None = None
    gate: GateReport | None = None
    eval: EvalReport | None = None
    skill_id: str | None = None


@dataclass
class Benchmark:
    """评测基准：输入样例 + 期望指标。"""

    benchmark_id: str
    task_type: str
    samples: list[dict[str, Any]]  # 每个 sample 含 input / expected
    metrics: dict[str, float] = field(default_factory=dict[str, float])


@dataclass
class QualityReport:
    """三维任务质量评测：完成度 / 正确性 / 轨迹质量。"""

    completion: float
    correctness: float
    trajectory: float
