"""进化引擎（L4 Evolution）—— 自进化结晶闭环。

诊断 → 提案 → 验证门 → 留出评测 四阶段，把 L3 循环运行轨迹结晶为技能/插件，
退化时溶解回退。对应规格 `openspec/specs/evolution/spec.md`。
"""

from .collector import Collector
from .curriculum import CurriculumPlanner, EvolutionGoal
from .diagnoser import Diagnoser
from .engine import EvolutionEngine, EvolutionTrigger
from .errors import EvolutionError, EvolutionErrorCode
from .evaluator import BenchmarkRegistry, BenchmarkScorer, Evaluator, QualityEvaluator
from .models import (
    GATE_CALIBER,
    Benchmark,
    DiagnosisReport,
    EvalReport,
    EvolutionOutcome,
    GateReport,
    GenerationCandidate,
    QualityReport,
    Trace,
    TraceRef,
)
from .observation import ObservationRegistry, ObservationWindow
from .pending import PendingItem, PendingQueue
from .plugin_ids import INTERNAL_PLUGIN_IDS
from .proposer import Proposer
from .validator import Validator
from .worker import EvolutionWorker

__all__ = [
    "Benchmark",
    "BenchmarkRegistry",
    "BenchmarkScorer",
    "Collector",
    "CurriculumPlanner",
    "Diagnoser",
    "DiagnosisReport",
    "EvalReport",
    "Evaluator",
    "EvolutionEngine",
    "EvolutionError",
    "EvolutionErrorCode",
    "EvolutionGoal",
    "EvolutionOutcome",
    "EvolutionTrigger",
    "EvolutionWorker",
    "GATE_CALIBER",
    "GateReport",
    "GenerationCandidate",
    "INTERNAL_PLUGIN_IDS",
    "ObservationRegistry",
    "PendingItem",
    "PendingQueue",
    "ObservationWindow",
    "Proposer",
    "QualityEvaluator",
    "QualityReport",
    "Trace",
    "TraceRef",
    "Validator",
]
