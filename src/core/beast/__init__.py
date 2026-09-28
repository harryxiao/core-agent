"""神兽召唤层（beast-mode）。

前台重大任务执行（pet-mode 后台重复简单任务的对偶）：20 个预定义山海经神兽，
各持独有神通（L3 Skill），召唤复用编排层 MultiAgentRouter.handoff 交接语义，
异步并发执行并据 LoopResult.failed 自动回归，多实例并发（兽间并行、兽内串行），
三入口激活（/summon 斜杠、summon <beast> [task] CLI、WebUI 自然语言）。

对应规格：doc/openspec/specs/beast-mode/spec.md
"""

from .activator import BeastActivator
from .errors import BeastError, BeastErrorCode
from .manager import BeastManager
from .models import Beast, BeastSessionState
from .registry import BeastRegistry
from .session import BeastSession
from .skills import build_innate_skills, register_innate_skills

__all__ = [
    "Beast",
    "BeastActivator",
    "BeastError",
    "BeastErrorCode",
    "BeastManager",
    "BeastRegistry",
    "BeastSession",
    "BeastSessionState",
    "build_innate_skills",
    "register_innate_skills",
]
