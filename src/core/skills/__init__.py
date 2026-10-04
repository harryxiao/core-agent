"""技能封装（L3 Skills）。

原子技能库 + 版本管理灰度/A/B + 技能路由 + 超时资源上限，是「记忆即光谱」
中 L3 技能段的管理层、结晶经济闭环的上半场。

对应规格：doc/openspec/specs/skills/spec.md
模块设计：doc/02-modules/skills.md
"""

from .crystallizer import SkillCrystallizer
from .errors import SkillError, SkillErrorCode
from .library import SkillLibrary
from .models import ABResult, Skill, SkillMatch
from .router import SkillRouter, SkillScorer
from .sop import SopExtractor, SopWriter, build_sop_prompt, sop_writer_with
from .version import VersionManager

__all__ = [
    "ABResult",
    "Skill",
    "SkillCrystallizer",
    "SkillError",
    "SkillErrorCode",
    "SkillLibrary",
    "SkillMatch",
    "SkillRouter",
    "SkillScorer",
    "SopExtractor",
    "SopWriter",
    "VersionManager",
    "build_sop_prompt",
    "sop_writer_with",
]
