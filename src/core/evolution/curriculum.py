"""自动课程（evolution）—— 冷路径的**目标选择层**。

回答「这一轮该迭代谁」：只吃**引擎内部的结构化信号**（本批失败计数 / 观察期目标 /
待确认候选），**不读记忆自由文本、不调模型**（change `0084` / 账本 E5 的裁决）。

产出的议程只作诊断**先验**：权重恒 < 1.0（每条失败证据计 1.0）⇒ **证据恒优先、先验只破并列**。
人显式指定的目标（`plan(explicit=…)`）是**指令**：直接采用、不参与竞争。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「自动课程」「对比诊断」
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from .models import GenerationCandidate, Trace
from .observation import ObservationRegistry

_TOP_WEIGHT = 0.5
"""议程首位的先验权重：< 1.0 ⇒ 先验解并列，但压不过任何一条失败证据。"""

_DIRECTIVE_WEIGHT = 1.0
"""显式目标的权重占位（`directive` 直接采用，权重不参与归因竞争）。"""

_DEFAULT_LIMIT = 3
"""议程预算上界：议程是「本轮候选池」而非全量排行（P5 token 有界）。"""

_HALVING = 2
"""位次 → 权重的几何衰减底数（0.5 / 0.25 / 0.125 …，恒 > 0 且 < 1）。"""


@dataclass(frozen=True)
class EvolutionGoal:
    """课程产出的一条迭代目标。

    `score` 是喂给诊断的**先验权重**（按议程位次几何递减，恒 < 1.0）；
    `directive=True` 的显式目标**直接采用**、不参与归因竞争；
    `reason` 是依据（失败数 / 已处理标记），供人读懂「为什么选它」。
    """

    plugin_id: str
    score: float
    reason: str
    directive: bool = False


class CurriculumPlanner:
    """课程规划器：结构化信号 → 有序、有界、确定的迭代目标议程。

    `observations` / `pending` 是**可调用/可读的引擎公开面**（缺省不注入 ⇒ 无降权信号）：
    `pending` 用可调用体（如 `engine.pending`）同 `PetWakeDriver(sessions=…)` 的先例 —— 每轮重取。
    """

    def __init__(
        self,
        *,
        observations: ObservationRegistry | None = None,
        pending: Callable[[], Sequence[GenerationCandidate]] | None = None,
    ) -> None:
        self._observations = observations
        self._pending = pending

    def plan(
        self,
        traces: Iterable[Trace],
        *,
        explicit: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[EvolutionGoal]:
        """生成议程：显式目标直采；否则按失败强度定序、已处理目标降权、位次给权重。"""
        if explicit is not None:
            return [EvolutionGoal(explicit, _DIRECTIVE_WEIGHT, "显式指定目标", directive=True)]
        counts = self._failure_counts(traces)
        if not counts:
            return []
        handled = self._handled()
        ranked = sorted(counts, key=lambda pid: (-counts[pid], pid in handled, pid))
        return [
            EvolutionGoal(
                plugin_id,
                _TOP_WEIGHT / _HALVING**rank,
                _reason(counts[plugin_id], handled.get(plugin_id)),
            )
            for rank, plugin_id in enumerate(ranked[: max(limit, 0)])
        ]

    @staticmethod
    def _failure_counts(traces: Iterable[Trace]) -> Counter[str]:
        """失败强度：只数**有插件归因的失败**（成功与无归因失败不产生目标）。"""
        return Counter(
            trace.plugin_id for trace in traces if not trace.success and trace.plugin_id is not None
        )

    def _handled(self) -> dict[str, str]:
        """已处理目标 → 依据：观察期中（已发布）/ 已有待确认候选（不重复生成同一目标）。"""
        handled: dict[str, str] = {}
        if self._observations is not None:
            for target in self._observations.targets():
                handled[target] = "观察期中"
        if self._pending is not None:
            for candidate in self._pending():
                handled.setdefault(candidate.target_plugin, "已有待确认候选")
        return handled


def _reason(failures: int, handled: str | None) -> str:
    """议程依据：失败数 + （若已处理）降权理由 —— 排序必须可解释。"""
    base = f"本批失败 {failures} 条"
    return f"{base}；已处理（{handled}）" if handled else base
