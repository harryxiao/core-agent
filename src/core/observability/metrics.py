"""性能指标监控（MetricsCollector）。

采集累计指标（inc）与瞬时指标（gauge），按 ``tags`` 维度（trace_id /
plugin_id / task_id）聚合，``snapshot`` 返回 ``{指标名: 值}`` 快照，
供进化评估与容量分析。

核心指标名约定：``task.completion_rate`` / ``token.used`` / ``loop.rounds`` /
``action.error_rate``。

对应接口：doc/03-interfaces/observability-interface.md §3
"""

from __future__ import annotations

from typing import TypeAlias

# tags 规范化后的维度键（按 key 排序，保证聚合稳定）
TagKey: TypeAlias = tuple[tuple[str, str], ...]


def _tag_key(tags: dict[str, str] | None) -> TagKey:
    if tags is None:
        return ()
    return tuple(sorted(tags.items()))


class MetricsCollector:
    """指标累计与快照聚合。"""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, TagKey], float] = {}
        self._gauges: dict[tuple[str, TagKey], float] = {}

    def inc(self, name: str, value: float = 1.0, *, tags: dict[str, str] | None = None) -> None:
        """累计指标（如 task_completed / token_used / error_count）。"""
        key = (name, _tag_key(tags))
        self._counters[key] = self._counters.get(key, 0.0) + value

    def gauge(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        """瞬时指标（如 loop_rounds / active_tasks）。"""
        key = (name, _tag_key(tags))
        self._gauges[key] = value

    def snapshot(self, *, tags: dict[str, str] | None = None) -> dict[str, float]:
        """按 tags 聚合返回指标快照；``tags=None`` 返回全部维度按名汇总。"""
        target = _tag_key(tags) if tags is not None else None
        out: dict[str, float] = {}
        for (name, tag_key), value in self._counters.items():
            if target is None or tag_key == target:
                out[name] = out.get(name, 0.0) + value
        for (name, tag_key), value in self._gauges.items():
            if target is None or tag_key == target:
                out[name] = value
        return out
