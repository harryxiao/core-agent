"""技能市场（L3 SkillHub）。

技能发现、多源路由健康回退、签名校验可信下载、发布审核流，是「记忆即光谱」
闭环的交换层：技能可发布到市场供其他实例下载，也可从市场获取他人沉淀的技能。

对应规格：doc/openspec/specs/skillhub/spec.md
模块设计：doc/02-modules/skillhub.md
"""

from .client import SkillHubClient
from .errors import SkillHubError, SkillHubErrorCode
from .index import MarketIndex
from .models import MarketSkill, MarketSource, SourceHealth
from .publisher import SkillPublisher
from .trust import TrustVerifier

__all__ = [
    "MarketIndex",
    "MarketSkill",
    "MarketSource",
    "SkillHubClient",
    "SkillHubError",
    "SkillHubErrorCode",
    "SkillPublisher",
    "SourceHealth",
    "TrustVerifier",
]
