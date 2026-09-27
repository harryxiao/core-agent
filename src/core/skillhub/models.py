"""技能市场数据模型（skillhub）。

定义市场技能元数据 / 市场源 / 源健康三组数据，供 MarketIndex /
SkillHubClient / SkillPublisher 消费。

对应接口：doc/03-interfaces/skillhub-interface.md §1 / §3
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketSkill:
    """市场技能元数据（不含完整技能体）。"""

    skill_id: str  # 全局唯一，如 "skills.data_analysis.summarize"
    name: str
    description: str
    version: str  # 市场版本 v1/v2...
    signature: str  # 签名摘要（TrustVerifier 校验用）
    source: str = "official"  # 来源（预留第三方源）
    status: str = "uploaded"  # uploaded | pending | published | rejected


@dataclass
class MarketSource:
    """市场源：一个技能目录。"""

    name: str
    skills: dict[str, MarketSkill] = field(default_factory=dict[str, MarketSkill])


@dataclass
class SourceHealth:
    """源健康探测结果。"""

    source: str
    healthy: bool
    last_check: str  # ISO 时间戳
