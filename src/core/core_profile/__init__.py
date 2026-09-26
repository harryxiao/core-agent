"""核心画像（core-profile）：Core-Agent 的灵魂文件（两级 Core.md）。

两级文件 + 双语义分区：宪法与全局规则 → ``constitution:v1`` coeffect 注入，
人格 → L0 记忆层，项目信息 → ContextEngine 上下文；项目级按 cwd 向上查找、
覆盖全局级；文件缺失静默降级、分区非法告警跳过。与 CLAUDE.md 分工并存。

对应规格：doc/openspec/specs/core-profile/spec.md
"""

from .engine import CoreProfileEngine
from .errors import ErrorCode
from .loader import GlobalProfileLoader, ProjectProfileLoader
from .models import AssembledProfile, CoreProfile, Section
from .profile import Merger, SectionParser, Validator

__all__ = [
    "AssembledProfile",
    "CoreProfile",
    "CoreProfileEngine",
    "ErrorCode",
    "GlobalProfileLoader",
    "Merger",
    "ProjectProfileLoader",
    "Section",
    "SectionParser",
    "Validator",
]
