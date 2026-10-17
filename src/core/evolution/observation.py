"""观察期回归采样（evolution）。

结晶**发布后**开启观察期窗口（记录发布时评测基线），调用方持续采样发布后的回归指标；
样本数达下限且观察均分低于「基线 − 容差」即判定回归——由 :class:`EvolutionEngine` 据此自动
``dissolve``，随后本注册表冻结该目标一个冷却期（期内不累积、不触发），避免溶解/重结晶抖动。

对应接口：doc/03-interfaces/evolution-interface.md §3.1 ｜ 规格 evolution/spec.md
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from core.persistence import read_state, write_state

# 回归判定门：观察样本下限 + 绝对分差容差（与 Evaluator.margin 同一形状）
_OBSERVE_MIN_SAMPLES = 3
_REGRESSION_TOLERANCE = 0.2

# 观察样本上界（滑动窗口）：超界淘汰最旧 —— 早期样本不得永久稀释/掩盖近期回归（change 0243）
_OBSERVE_MAX_SAMPLES = 64

# 溶解后该方向的冻结冷却期（秒）
_FREEZE_COOLDOWN_S = 300.0


@dataclass
class ObservationWindow:
    """一个产物的观察期窗口：基线 + 窗口内实测样本 + 冻结截止。"""

    target: str
    baseline: float
    samples: list[float] = field(default_factory=list[float])
    frozen_until: float = 0.0

    @property
    def mean(self) -> float:
        """窗口内观察均分（无样本 → 0.0）；样本受 ``max_samples`` 约束，只反映最近样本。"""
        return sum(self.samples) / len(self.samples) if self.samples else 0.0


class ObservationRegistry:
    """观察期窗口注册表：开窗 / 采样判定 / 冻结；可落盘（注入 ``path``，缺省纯内存）。"""

    def __init__(
        self,
        *,
        min_samples: int = _OBSERVE_MIN_SAMPLES,
        tolerance: float = _REGRESSION_TOLERANCE,
        cooldown_s: float = _FREEZE_COOLDOWN_S,
        max_samples: int = _OBSERVE_MAX_SAMPLES,
        path: Path | None = None,
    ) -> None:
        self._min_samples = min_samples
        self._tolerance = tolerance
        self._cooldown_s = cooldown_s
        self._max_samples = max_samples
        self._path = path
        self._windows: dict[str, ObservationWindow] = {}
        self._load()

    def open(self, target: str, *, baseline: float) -> ObservationWindow:
        """开窗（重新发布即重新起算基线，覆盖旧窗口）。"""
        window = ObservationWindow(target=target, baseline=baseline)
        self._windows[target] = window
        self._persist()
        return window

    def window(self, target: str) -> ObservationWindow | None:
        """取窗口；未开窗返回 None。"""
        return self._windows.get(target)

    def targets(self) -> list[str]:
        """当前已开窗的目标（供采样侧按目标归因上报）。"""
        return list(self._windows)

    def sample(self, target: str, score: float, *, now: float | None = None) -> bool:
        """记一次观察样本，返回**是否触发回归**（未开窗 / 冻结期内的样本一律忽略）。"""
        window = self._windows.get(target)
        if window is None:
            return False
        if (now if now is not None else time.time()) < window.frozen_until:
            return False
        window.samples.append(score)
        self._trim(window)
        self._persist()
        return self._regressed(window)

    def freeze(self, target: str, *, now: float | None = None) -> None:
        """冻结该方向一个冷却期（并清零样本，避免冷却结束即二次触发）。"""
        window = self._windows.get(target)
        if window is None:
            return
        window.samples.clear()
        window.frozen_until = (now if now is not None else time.time()) + self._cooldown_s
        self._persist()

    # ---- 落盘 ----

    def _load(self) -> None:
        """恢复落盘窗口（含冻结截止）；缺失 / 损坏 / 结构不符 → 无窗口（不抛）。"""
        raw = read_state(self._path)
        try:
            windows: dict[str, ObservationWindow] = {}
            for target, item in raw.items():
                window = ObservationWindow(
                    target=str(target),
                    baseline=float(item["baseline"]),
                    samples=[float(score) for score in item.get("samples", [])],
                    frozen_until=float(item.get("frozen_until", 0.0)),
                )
                self._trim(window)  # 旧窗口（更大上界）恢复时同样裁剪
                windows[str(target)] = window
            self._windows = windows
        except (AttributeError, KeyError, TypeError, ValueError):
            self._windows = {}

    def _trim(self, window: ObservationWindow) -> None:
        """把样本裁到最近 ``max_samples`` 条（淘汰最旧）。"""
        overflow = len(window.samples) - self._max_samples
        if overflow > 0:
            del window.samples[:overflow]

    def _persist(self) -> None:
        write_state(
            self._path,
            {
                target: {
                    "baseline": window.baseline,
                    "samples": list(window.samples),
                    "frozen_until": window.frozen_until,
                }
                for target, window in self._windows.items()
            },
        )

    def _regressed(self, window: ObservationWindow) -> bool:
        """样本达下限且均分低于「基线 − 容差」。"""
        if len(window.samples) < self._min_samples:
            return False
        return window.mean < window.baseline - self._tolerance
