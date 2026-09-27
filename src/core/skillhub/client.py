"""技能市场客户端（SkillHubClient）。

搜索市场技能（不拉取完整技能体）+ 可信下载（先校验签名再注册，失败拒绝
且不落盘）。下载初始状态恒为 draft，需本地显式激活后进入可用技能集。

对应接口：doc/03-interfaces/skillhub-interface.md §2
"""

from __future__ import annotations

from collections.abc import Callable

from core.skills import Skill, SkillLibrary

from .errors import SkillHubError, SkillHubErrorCode
from .index import MarketIndex
from .models import MarketSkill
from .trust import TrustVerifier

Fetcher = Callable[[str, str], Skill | None]


class SkillHubClient:
    """技能市场客户端：搜索 + 可信下载。"""

    def __init__(
        self,
        library: SkillLibrary,
        *,
        index: MarketIndex | None = None,
        verifier: TrustVerifier | None = None,
        fetcher: Fetcher | None = None,
    ) -> None:
        self._library = library
        self._index = index if index is not None else MarketIndex()
        self._verifier = verifier if verifier is not None else TrustVerifier()
        self._fetcher = fetcher

    def search(self, query: str, *, source: str = "official", top_k: int = 20) -> list[MarketSkill]:
        """按 query 搜索市场技能，返回元数据列表（不拉取完整技能体）。"""
        terms = query.lower().split()
        scored: list[tuple[int, MarketSkill]] = []
        for market in self._index.list(source=source):
            haystack = f"{market.name} {market.description} {market.skill_id}".lower()
            hits = sum(1 for t in terms if t in haystack)
            if hits > 0:
                scored.append((hits, market))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [market for _hits, market in scored[:top_k]]

    def download(self, skill_id: str, *, source: str = "official") -> Skill:
        """校验签名 → SkillLibrary.register(status="draft")；签名失败抛 SIGNATURE_INVALID。"""
        market = self._index.get(source, skill_id)
        if market is None or self._fetcher is None:
            raise SkillHubError(
                SkillHubErrorCode.SIGNATURE_INVALID,
                f"无法下载技能（市场缺失或未接入拉取）: {skill_id}",
            )
        skill = self._fetcher(skill_id, source)
        if skill is None:
            raise SkillHubError(SkillHubErrorCode.SIGNATURE_INVALID, f"拉取技能失败: {skill_id}")
        if not self._verifier.verify(skill, market.signature):
            raise SkillHubError(
                SkillHubErrorCode.SIGNATURE_INVALID, f"签名校验失败，拒绝下载: {skill_id}"
            )
        skill.status = "draft"
        self._library.register(skill)
        return skill
