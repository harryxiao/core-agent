"""市场索引（MarketIndex）。

按 source 路由到对应市场源、按源列目录、源健康探测与回退。源不存在拒绝
路由（SOURCE_NOT_FOUND），源不可达标记不健康并回退官方源（SOURCE_UNHEALTHY）。

对应接口：doc/03-interfaces/skillhub-interface.md §3
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from .errors import SkillHubError, SkillHubErrorCode
from .models import MarketSkill, MarketSource, SourceHealth

HealthProbe = Callable[[str], bool]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MarketIndex:
    """市场索引：多源路由 + 健康探测 + 目录列出。"""

    def __init__(
        self,
        sources: dict[str, MarketSource] | None = None,
        *,
        health_probe: HealthProbe | None = None,
    ) -> None:
        self._sources = dict(sources) if sources else {"official": MarketSource(name="official")}
        self._health_probe = health_probe
        self._health: dict[str, SourceHealth] = {}

    def list(self, *, source: str = "official") -> list[MarketSkill]:
        """列出指定源的技能目录元数据。"""
        self._ensure_healthy(source)
        return list(self._sources[source].skills.values())

    def route(self, source: str) -> MarketSource:
        """按 source 路由到对应市场源；源不存在抛 SOURCE_NOT_FOUND。"""
        self._ensure_healthy(source)
        return self._sources[source]

    def health(self, source: str) -> SourceHealth:
        """源健康探测；不可达标记不健康（SOURCE_UNHEALTHY 由 list/route 触发回退）。"""
        src = self._sources.get(source)
        if src is None:
            raise SkillHubError(SkillHubErrorCode.SOURCE_NOT_FOUND, f"source 不存在: {source}")
        result = SourceHealth(source=source, healthy=self._probe(source), last_check=_now())
        self._health[source] = result
        return result

    # ---- 发布方辅助（非接口面，供 SkillPublisher 使用） ----

    def put(self, source: str, skill: MarketSkill) -> None:
        """把市场技能元数据写入指定源。"""
        src = self._sources.get(source)
        if src is None:
            raise SkillHubError(SkillHubErrorCode.SOURCE_NOT_FOUND, f"source 不存在: {source}")
        src.skills[skill.skill_id] = skill

    def get(self, source: str, skill_id: str) -> MarketSkill | None:
        """按源取市场技能元数据；源或技能不存在返回 None。"""
        src = self._sources.get(source)
        return None if src is None else src.skills.get(skill_id)

    # ---- 内部辅助 ----

    def _ensure_healthy(self, source: str) -> None:
        if source not in self._sources:
            raise SkillHubError(SkillHubErrorCode.SOURCE_NOT_FOUND, f"source 不存在: {source}")
        if not self._probe(source):
            raise SkillHubError(
                SkillHubErrorCode.SOURCE_UNHEALTHY, f"来源不可达（回退官方源）: {source}"
            )

    def _probe(self, source: str) -> bool:
        if self._health_probe is None:
            return True
        return bool(self._health_probe(source))
