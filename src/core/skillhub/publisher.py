"""技能发布（SkillPublisher）。

发布进入审核流 uploaded → pending → published/rejected；审核通过版本提升
（v1→v2），驳回状态回退（允许修改后重传）。

发布的技能体可入库到本地市场制品库（注入 ``artifacts``），供消费侧拉取；
审核定位发布源的真源是**市场目录**（非进程内记忆），故审核跨进程可续。

对应接口：doc/03-interfaces/skillhub-interface.md §4
"""

from __future__ import annotations

from dataclasses import replace

from core.skills import Skill, SkillLibrary, VersionManager

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
        artifacts: SkillLibrary | None = None,
    ) -> None:
        self._index = index if index is not None else MarketIndex()
        self._verifier = verifier if verifier is not None else TrustVerifier()
        self._version_manager = version_manager
        self._artifacts = artifacts

    def publish(self, skill: Skill, *, source: str = "official") -> str:
        """上传技能 → status=pending；技能体入本地市场制品库；返回 skill_id。"""
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
        # 先上架后入库：源不存在时抛 SOURCE_NOT_FOUND，此时不留半份制品。
        self._index.put(source, market)
        if self._artifacts is not None:
            self._artifacts.register(replace(skill))  # 存副本，勿与本地技能库共享对象
        return skill.skill_id

    def review(self, skill_id: str, decision: str) -> None:
        """审核：approved → published（版本 v1→v2）；rejected → 状态回退。"""
        located = self._index.locate(skill_id)
        if located is None:
            raise SkillHubError(
                SkillHubErrorCode.SKILL_NOT_ACTIVE, f"技能未发布（未激活），无法审核: {skill_id}"
            )
        source, market = located
        if decision == "approved":
            market.status = "published"
            market.version = _bump_version(market.version)
            self._sync_artifact(skill_id, market)
            self._index.put(source, market)
            if self._version_manager is not None:
                self._version_manager.promote(skill_id, market.version, 1.0)
        elif decision == "rejected":
            market.status = "rejected"
            self._index.put(source, market)
            raise SkillHubError(SkillHubErrorCode.PUBLISH_REJECTED, f"发布被驳回: {skill_id}")
        else:
            raise SkillHubError(SkillHubErrorCode.PUBLISH_REJECTED, f"非法审核决定: {decision}")

    # ---- 内部辅助 ----

    def _sync_artifact(self, skill_id: str, market: MarketSkill) -> None:
        """把制品本体提升到市场版本并**重新签名**（验签仍成立）；无制品则不动。"""
        if self._artifacts is None:
            return
        try:
            body = self._artifacts.lookup(skill_id)
        except KeyError:
            return
        body.version = market.version
        market.signature = self._verifier.sign(body)
        self._artifacts.register(body)
