"""留出评测 + 评测基建（evolution）。

`BenchmarkRegistry` 基准集注册/基线分；`QualityEvaluator` 三维任务质量评测
（完成度/正确性/轨迹质量）；`Evaluator` 留出集评测 + 并发资源上限（Semaphore），
verdict=publish/rollback/freeze。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md
「留出评测 / 评测基建 / 任务质量评测」
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, cast

from .models import Benchmark, EvalReport, GenerationCandidate, QualityReport


class BenchmarkRegistry:
    """基准集注册 + 基线分管理。"""

    def __init__(self) -> None:
        self._benchmarks: dict[str, Benchmark] = {}
        self._baselines: dict[str, float] = {}

    def register(self, benchmark: Benchmark) -> None:
        self._benchmarks[benchmark.benchmark_id] = benchmark

    def benchmark_for(self, task_type: str) -> Benchmark | None:
        for b in self._benchmarks.values():
            if b.task_type == task_type:
                return b
        return None

    def set_baseline(self, plugin_id: str, score: float) -> None:
        self._baselines[plugin_id] = score

    def baseline_score(self, plugin_id: str) -> float:
        return self._baselines.get(plugin_id, 0.0)

    def list(self) -> list[Benchmark]:
        """返回已注册基准集列表（留出评测按需引用）。"""
        return list(self._benchmarks.values())


class QualityEvaluator:
    """三维任务质量评测：完成度 / 正确性 / 轨迹质量。"""

    def score(
        self,
        *,
        goal_reached: bool,
        result: Any = None,
        expected: Any = None,
        trajectory: list[Any] | None = None,
    ) -> QualityReport:
        completion = 1.0 if goal_reached else 0.0
        correctness = 0.0
        if expected is not None:
            correctness = 1.0 if result == expected else 0.0
        return QualityReport(
            completion=completion,
            correctness=correctness,
            trajectory=self._trajectory_score(trajectory),
        )

    @staticmethod
    def _trajectory_score(trajectory: list[Any] | None) -> float:
        if not trajectory:
            return 1.0
        failed = sum(
            1
            for s in trajectory
            if isinstance(s, dict) and cast("dict[str, object]", s).get("failed")
        )
        return max(0.0, 1.0 - failed / len(trajectory))


class Evaluator:
    """留出评测器：基线对比判定退化，批量评测受并发上限约束。"""

    plugin_id = "evolution.evaluator"

    def __init__(
        self,
        *,
        registry: BenchmarkRegistry | None = None,
        quality: QualityEvaluator | None = None,
        score_fn: Callable[[GenerationCandidate], float] | None = None,
        max_concurrency: int = 4,
        margin: float = 0.0,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency 必须 ≥ 1")  # noqa: TRY003 — 配置守卫，非领域错误码
        self._registry = registry if registry is not None else BenchmarkRegistry()
        self._quality = quality if quality is not None else QualityEvaluator()
        self._score_fn = score_fn
        self._max_concurrency = max_concurrency
        self._margin = margin

    def evaluate(self, candidate: GenerationCandidate) -> EvalReport:
        baseline = self._registry.baseline_score(candidate.target_plugin)
        held_out = self._held_out_score(candidate)
        if held_out < baseline - self._margin:
            return EvalReport(
                passed=False,
                held_out_score=held_out,
                baseline_score=baseline,
                verdict="rollback",
            )
        return EvalReport(
            passed=True,
            held_out_score=held_out,
            baseline_score=baseline,
            verdict="publish",
        )

    async def aevaluate(self, candidate: GenerationCandidate) -> EvalReport:
        """异步留出评测（批量/并发路径，测试可子类化重写以追踪并发）。"""
        return self.evaluate(candidate)

    async def evaluate_batch(self, candidates: list[GenerationCandidate]) -> list[EvalReport]:
        sem = asyncio.Semaphore(self._max_concurrency)
        return await asyncio.gather(*(self._bounded(c, sem) for c in candidates))

    async def _bounded(self, candidate: GenerationCandidate, sem: asyncio.Semaphore) -> EvalReport:
        async with sem:
            return await self.aevaluate(candidate)

    def _held_out_score(self, candidate: GenerationCandidate) -> float:
        if self._score_fn is not None:
            return self._score_fn(candidate)
        return 0.0
