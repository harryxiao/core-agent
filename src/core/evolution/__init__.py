"""进化引擎（L4 Evolution）—— 自进化结晶闭环。

诊断 → 提案 → 验证门 → 留出评测 四阶段，把 L3 循环运行轨迹结晶为技能/插件，
退化时溶解回退。对应规格 `openspec/specs/evolution/spec.md`。
"""

from .collector import Collector
from .diagnoser import Diagnoser
from .engine import EvolutionEngine, EvolutionTrigger
from .errors import EvolutionError, EvolutionErrorCode
from .evaluator import BenchmarkRegistry, Evaluator, QualityEvaluator
from .models import (
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
from .proposer import Proposer
from .validator import Validator
from .worker import EvolutionWorker

__all__ = [
    "Benchmark",
    "BenchmarkRegistry",
    "Collector",
    "Diagnoser",
    "DiagnosisReport",
    "EvalReport",
    "Evaluator",
    "EvolutionEngine",
    "EvolutionError",
    "EvolutionErrorCode",
    "EvolutionOutcome",
    "EvolutionTrigger",
    "EvolutionWorker",
    "GateReport",
    "GenerationCandidate",
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
