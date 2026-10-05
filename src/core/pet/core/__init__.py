"""宠物模式核心（pet-core）：后台自治循环 + 多宠物调度。

四层架构（基础属性层 / 自主目标循环层 / 探索工具集层 / 安全边界层）解耦；
PetSession 承载生命周期，PetActivator 收口三入口，PetManager 多宠物隔离。

对应规格：doc/openspec/specs/pet-mode/spec.md
"""

from .activator import PetActivator
from .driver import FAILED, SKIPPED, WOKEN, PetWakeDriver, WakeOutcome
from .errors import PetError, PetErrorCode
from .layers import ExplorerLayer, PersonaLayer, SafetyDecision, SafetyLayer
from .manager import PetManager
from .models import PetSessionState, PetTask, PetTaskKind
from .session import PetSession

__all__ = [
    "FAILED",
    "SKIPPED",
    "WOKEN",
    "ExplorerLayer",
    "PersonaLayer",
    "PetActivator",
    "PetError",
    "PetErrorCode",
    "PetManager",
    "PetSession",
    "PetSessionState",
    "PetTask",
    "PetTaskKind",
    "PetWakeDriver",
    "SafetyDecision",
    "SafetyLayer",
    "WakeOutcome",
]
