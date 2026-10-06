"""CI/CD 交付流水线（ci-cd）：质量门禁 + 制品发布。"""

from .errors import CiCdError, CiCdErrorCode
from .models import Artifact, Gate, GateResult, PipelineRun
from .pipeline import (
    CRYSTALLIZATION_GATE_MARKS,
    GATE_COMMANDS,
    CICDPipeline,
    SubprocessGateExecutor,
    build_gate_executor,
    crystallization_gates,
)
from .publisher import ArtifactPublisher

__all__ = [
    "Artifact",
    "ArtifactPublisher",
    "CiCdError",
    "CiCdErrorCode",
    "CICDPipeline",
    "CRYSTALLIZATION_GATE_MARKS",
    "GATE_COMMANDS",
    "Gate",
    "GateResult",
    "PipelineRun",
    "SubprocessGateExecutor",
    "build_gate_executor",
    "crystallization_gates",
]
