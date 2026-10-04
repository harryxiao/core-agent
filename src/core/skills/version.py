"""版本管理与灰度/A/B（VersionManager）。

技能世代版本：灰度发布（新版本仅对 ratio 比例任务生效）、A/B 并行对比
（指标量化），B 退化自动回退稳定版并标记 deprecated。

灰度 / A-B / 稳定版状态可落盘（注入 ``path``）：变更即落盘、启动即恢复；
缺省 ``path=None`` 纯内存（见 ``persist``）。

对应接口：doc/03-interfaces/skills-interface.md §3
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .library import SkillLibrary
from .models import ABResult
from .persist import read_state, write_state

MetricFn = Callable[[str, str], float]


class VersionManager:
    """技能版本管理：灰度发布 + A/B 测试 + 版本选择。"""

    def __init__(
        self,
        library: SkillLibrary | None = None,
        *,
        metrics: MetricFn | None = None,
        rng: Callable[[], float] | None = None,
        path: Path | None = None,
    ) -> None:
        self._library = library
        self._metrics = metrics
        self._rng = rng if rng is not None else random.random
        self._path = path
        self._gray: dict[str, tuple[str, float]] = {}
        self._stable: dict[str, str] = {}
        self._ab: dict[str, ABResult] = {}
        self._load()

    def promote(self, skill_id: str, version: str, ratio: float) -> None:
        """灰度发布：新版本仅对 ratio 比例任务生效。"""
        self._gray[skill_id] = (version, ratio)
        self._persist()

    def ab_test(self, skill_id: str, v_a: str, v_b: str) -> ABResult:
        """A/B 并行对比；B 指标退化自动回退稳定版 A 并标记 B deprecated。"""
        a = self._metric(skill_id, v_a)
        b = self._metric(skill_id, v_b)
        delta = {"a": a, "b": b}
        if b < a:
            result = ABResult(winner=v_a, metric_delta=delta, decision="revert")
            self._deprecate(skill_id, v_b)
            self._stable[skill_id] = v_a
        elif b > a:
            result = ABResult(winner=v_b, metric_delta=delta, decision="promote")
            self._stable[skill_id] = v_b
        else:
            result = ABResult(winner=v_a, metric_delta=delta, decision="keep")
            self._stable[skill_id] = v_a
        self._ab[skill_id] = result
        self._persist()
        return result

    def select(self, skill_id: str, ctx: dict[str, Any]) -> str:
        """按 A/B 结果 / 灰度 / 稳定版优先级返回应使用的版本。"""
        result = self._ab.get(skill_id)
        if result is not None and result.winner is not None:
            return result.winner
        gray = self._gray.get(skill_id)
        if gray is not None:
            version, ratio = gray
            if self._rng() < ratio:
                return version
        stable = self._stable.get(skill_id)
        if stable is not None:
            return stable
        return self._current(skill_id)

    # ---- 落盘 ----

    def _load(self) -> None:
        """恢复落盘状态；缺失 / 损坏 / 结构不符 → 空态（不抛，见 ``persist``）。"""
        raw = read_state(self._path)
        try:
            gray = {
                str(skill_id): (str(version), float(ratio))
                for skill_id, (version, ratio) in raw.get("gray", {}).items()
            }
            stable = {str(skill_id): str(version) for skill_id, version in raw["stable"].items()}
            ab = {str(skill_id): ABResult(**item) for skill_id, item in raw["ab"].items()}
        except (AttributeError, KeyError, TypeError, ValueError):
            return
        self._gray.update(gray)
        self._stable.update(stable)
        self._ab.update(ab)

    def _persist(self) -> None:
        write_state(
            self._path,
            {
                "gray": {sid: [ver, ratio] for sid, (ver, ratio) in self._gray.items()},
                "stable": self._stable,
                "ab": {sid: asdict(result) for sid, result in self._ab.items()},
            },
        )

    # ---- 内部辅助 ----

    def _metric(self, skill_id: str, version: str) -> float:
        if self._metrics is None:
            return 0.0
        return float(self._metrics(skill_id, version))

    def _deprecate(self, skill_id: str, version: str) -> None:
        if self._library is None:
            return
        try:
            skill = self._library.lookup(skill_id)
        except KeyError:
            return
        if skill.version == version:
            skill.status = "deprecated"

    def _current(self, skill_id: str) -> str:
        if self._library is None:
            return ""
        try:
            return self._library.lookup(skill_id).version
        except KeyError:
            return ""
