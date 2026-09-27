"""技能发布（SkillPublisher）。

发布进入审核流 uploaded → pending → published/rejected；审核通过版本提升
（v1→v2），驳回状态回退（允许修改后重传）。

对应接口：doc/03-interfaces/skillhub-interface.md §4
"""

from __future__ import annotations

from core.skills import Skill, VersionManager

from .errors import SkillHubError, SkillHubErrorCode
from .index import MarketIndex
from .models import MarketSkill
from .trust import TrustVerifier


def _bump_version(version: str) -> str:
    """把 "v1" 提升为 "v2"（世代版本递增）。"""
    if version.startswith("v") and version[1:].isdigit():
        return f"v{int(version[1:]) + 1}"
    return f"{version}+1"


class SkillPublisher:
    """技能发布：上传 → 审核流 → 发布/驳回。"""

    def __init__(
        self,
        *,
        index: MarketIndex | None = None,
        verifier: TrustVerifier | None = None,
        version_manager: VersionManager | None = None,
    ) -> None:
        self._index = index if index is not None else MarketIndex()
        self._verifier = verifier if verifier is not None else TrustVerifier()
        self._version_manager = version_manager
        self._published: dict[str, str] = {}  # skill_id → source

    def publish(self, skill: Skill, *, source: str = "official") -> str:
        """上传技能 → status=pending，进入审核流；返回 skill_id。"""
        signature = self._verifier.sign(skill)
        market = MarketSkill(
            skill_id=skill.skill_id,
            name=skill.skill_id.rsplit(".", 1)[-1],
            description=skill.description,
            version=skill.version,
            signature=signature,
            source=source,
            status="pending",
        )
        self._index.put(source, market)
        self._published[skill.skill_id] = source
        return skill.skill_id

    def review(self, skill_id: str, decision: str) -> None:
        """审核：approved → published（版本 v1→v2）；rejected → 状态回退。"""
        source = self._published.get(skill_id)
        if source is None:
            raise SkillHubError(
                SkillHubErrorCode.SKILL_NOT_ACTIVE, f"技能未发布（未激活），无法审核: {skill_id}"
            )
        market = self._index.get(source, skill_id)
        if market is None:
            raise SkillHubError(SkillHubErrorCode.SKILL_NOT_ACTIVE, f"技能不存在: {skill_id}")
        if decision == "approved":
            market.status = "published"
            market.version = _bump_version(market.version)
            if self._version_manager is not None:
                self._version_manager.promote(skill_id, market.version, 1.0)
        elif decision == "rejected":
            market.status = "rejected"
            raise SkillHubError(SkillHubErrorCode.PUBLISH_REJECTED, f"发布被驳回: {skill_id}")
        else:
            raise SkillHubError(SkillHubErrorCode.PUBLISH_REJECTED, f"非法审核决定: {decision}")
