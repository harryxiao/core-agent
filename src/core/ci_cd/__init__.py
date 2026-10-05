"""CI/CD 交付流水线（ci-cd）：质量门禁 + 制品发布。"""

from .errors import CiCdError, CiCdErrorCode
from .models import Artifact, Gate, GateResult, PipelineRun
from .pipeline import GATE_COMMANDS, CICDPipeline, SubprocessGateExecutor, build_gate_executor
from .publisher import ArtifactPublisher

__all__ = [
    "Artifact",
    "ArtifactPublisher",
    "CiCdError",
    "CiCdErrorCode",
    "CICDPipeline",
    "GATE_COMMANDS",
    "Gate",
    "GateResult",
    "PipelineRun",
    "SubprocessGateExecutor",
    "build_gate_executor",
]
