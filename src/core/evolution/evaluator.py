"""留出评测 + 评测基建（evolution）。

`BenchmarkRegistry` 基准集注册/基线分（**可落盘**：跨进程可读，本 change 0119）；`QualityEvaluator`
三维任务质量评测（完成度/正确性/轨迹质量）；`BenchmarkScorer` 基准执行器面（逐样本真实执行 →
聚合留出分，**无法评测 ⇒ `None`**）；`Evaluator` 留出集评测 + 并发资源上限（Semaphore），
verdict=publish/rollback/freeze。

**数据面与执行面分离**（change 0119）：基准集与基线是**数据**（人工/运维注册、随 `$CORE_STATE_DIR`
单文件落盘、跨进程可读），基准样本的**执行器**是**受信代码**（由组合根或运维注入 `runners`
映射），**不**随数据面落盘。故「有基准但无执行器 / 无基线」= 无法评测（fail-closed），
不产出假分数、也不谎报退化。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md
「留出评测 / 评测基建 / 任务质量评测」
"""

from __future__ import annotations

import asyncio
import json
import warnings
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from core.persistence import write_state

from .models import Benchmark, EvalReport, GenerationCandidate, QualityReport

_BENCHMARK_STATE_VERSION = 1


class BenchmarkRegistry:
    """基准集注册 + 基线分管理（``path`` 非空 ⇒ 单文件 JSON 落盘，跨进程可读）。

    落盘缺失 ⇒ 空基准集（**不**告警）；落盘**损坏/结构不符** ⇒ 降级为空基准集并 ``warnings.warn``
    （不抛、不阻断启动 —— 与 ``plugins/installs.py`` 同款降级策略）。未注入路径（``path=None``）
    纯内存（既有调用方零行为变化）。
    """

    def __init__(self, *, path: Path | None = None) -> None:
        self._path = path
        self._benchmarks: dict[str, Benchmark] = {}
        self._baselines: dict[str, float] = {}
        self._load()

    def register(self, benchmark: Benchmark) -> None:
        """登记基准（绑定 ``plugin_id`` 者只对同目标的候选生效），并落盘。"""
        self._benchmarks[benchmark.benchmark_id] = benchmark
        self._persist()

    def benchmark_for(self, task_type: str) -> Benchmark | None:
        for b in self._benchmarks.values():
            if b.task_type == task_type:
                return b
        return None

    def benchmark_for_plugin(self, plugin_id: str) -> Benchmark | None:
        """按候选归因目标取**绑定**的基准；未绑定 ⇒ ``None``（不回落「任意基准」）。"""
        for b in self._benchmarks.values():
            if b.plugin_id == plugin_id:
                return b
        return None

    def set_baseline(self, plugin_id: str, score: float) -> None:
        """为某归因目标设置基线分（退化判定的**绝对阈值**），并落盘。"""
        self._baselines[plugin_id] = score
        self._persist()

    def baseline_of(self, plugin_id: str) -> float | None:
        """已注册的基线分；**未注册 ⇒ ``None``**（无对比面 ⇒ 无法评测，不静默按 `0.0` 放行）。"""
        return self._baselines.get(plugin_id)

    def baseline_score(self, plugin_id: str) -> float:
        return self._baselines.get(plugin_id, 0.0)

    def list(self) -> list[Benchmark]:
        """返回已注册基准集列表（留出评测按需引用）。"""
        return list(self._benchmarks.values())

    # ---- 落盘 ----

    def _load(self) -> None:
        """恢复落盘基准集与基线；缺失 → 空态（静默）；损坏/结构不符 → 空态 + 告警。"""
        if self._path is None or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.warn(f"基准集落盘不可读，已忽略: {self._path}（{exc}）", stacklevel=2)
            return
        data: Any = raw
        if not isinstance(data, dict):
            warnings.warn(f"基准集落盘格式非法，已忽略: {self._path}", stacklevel=2)
            return
        entries = cast("dict[str, Any]", data).get("benchmarks")
        if not isinstance(entries, list):
            warnings.warn(f"基准集落盘格式非法，已忽略: {self._path}", stacklevel=2)
            return
        for entry in cast("list[Any]", entries):
            benchmark = self._entry_to_benchmark(entry)
            if benchmark is not None:
                self._benchmarks[benchmark.benchmark_id] = benchmark
        baselines = cast("dict[str, Any]", data).get("baselines")
        self._load_baselines(baselines)

    def _load_baselines(self, raw: Any) -> None:
        """恢复基线表（非数值条目跳过 —— 坏值不静默采纳为基线）。"""
        if not isinstance(raw, dict):
            return
        for plugin_id, score in cast("dict[str, Any]", raw).items():
            try:
                self._baselines[str(plugin_id)] = float(score)
            except (TypeError, ValueError):
                continue

    def _entry_to_benchmark(self, entry: Any) -> Benchmark | None:
        """单条基准：残缺条目**告警并跳过**（不静默丢）。"""
        if not isinstance(entry, dict):
            warnings.warn(f"基准集条目残缺，已跳过: {entry!r}", stacklevel=2)
            return None
        data = cast("dict[str, Any]", entry)
        benchmark_id = str(data.get("benchmark_id") or "")
        task_type = str(data.get("task_type") or "")
        if not benchmark_id or not task_type:
            warnings.warn(f"基准集条目残缺，已跳过: {entry!r}", stacklevel=2)
            return None
        samples: list[dict[str, Any]] = [
            dict(cast("dict[str, Any]", s))
            for s in cast("list[Any]", data.get("samples") or [])
            if isinstance(s, dict)
        ]
        plugin_id = data.get("plugin_id")
        return Benchmark(
            benchmark_id=benchmark_id,
            task_type=task_type,
            samples=samples,
            # metrics 的落盘形状是 JSON 对象；非数值条目在此载入与后续使用中均不参与判定
            metrics={
                str(k): float(v)
                for k, v in cast("dict[str, Any]", data.get("metrics") or {}).items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            },
            plugin_id=str(plugin_id) if plugin_id else None,
        )

    def _persist(self) -> None:
        if self._path is None:
            return
        write_state(
            self._path,
            {
                "version": _BENCHMARK_STATE_VERSION,
                "benchmarks": [
                    {
                        "benchmark_id": b.benchmark_id,
                        "task_type": b.task_type,
                        "plugin_id": b.plugin_id,
                        "samples": list(b.samples),
                        "metrics": dict(b.metrics),
                    }
                    for b in self._benchmarks.values()
                ],
                "baselines": dict(self._baselines),
            },
        )


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


# 基准样本执行器：收一个样本（含 input / expected），返回该样本的**实际结果**（受信代码）
Runner = Callable[[dict[str, Any]], Any]


class BenchmarkScorer:
    """基准执行器面：逐样本**真实执行** → 与期望对比 → 聚合出留出分。

    ``runners`` 是 `task_type` → 可调用体的映射，**由组合根或运维注入**（执行面是受信代码，
    不随基准集落盘）；执行器收到一个样本，返回该样本的实际结果。样本分 = ``QualityEvaluator``
    三维分的均值（完成度 = 执行器**产出非空**；正确性 = 结果与样本 ``expected`` 相等；无轨迹面
    ⇒ 轨迹维度恒 1.0），留出分 = 各样本分的均值。

    **无法评测 ⇒ 返回 `None`**（不产出分数）：候选无**绑定**基准 / 基准无样本 / 该 `task_type`
    无执行器。执行器抛异常**冒泡**（不吞成 0 分、也不吞成通过）—— 评测器据此判 `freeze`。
    """

    def __init__(
        self,
        registry: BenchmarkRegistry,
        *,
        quality: QualityEvaluator | None = None,
        runners: Mapping[str, Runner] | None = None,
    ) -> None:
        self._registry = registry
        self._quality = quality if quality is not None else QualityEvaluator()
        self._runners: Mapping[str, Runner] = runners if runners is not None else {}

    def __call__(self, candidate: GenerationCandidate) -> float | None:
        benchmark = self._registry.benchmark_for_plugin(candidate.target_plugin)
        if benchmark is None or not benchmark.samples:
            return None
        runner = self._runners.get(benchmark.task_type)
        if runner is None:
            return None
        scores: list[float] = []
        for sample in benchmark.samples:
            result = runner(sample)
            report = self._quality.score(
                goal_reached=result is not None,
                result=result,
                expected=sample.get("expected"),
            )
            scores.append((report.completion + report.correctness + report.trajectory) / 3)
        return sum(scores) / len(scores)


class Evaluator:
    """留出评测器：基线对比判定退化，批量评测受并发上限约束。

    三态（`EvalReport.verdict`）：`publish`（不退化）/ `rollback`（已判退化）/ **`freeze`
    （无法评测）** —— 后者是**无法产出留出分**时的 fail-closed 结论，SHALL NOT 被当作退化
    （无证据），SHALL NOT 被当作通过。
    """

    plugin_id = "evolution.evaluator"

    def __init__(
        self,
        *,
        registry: BenchmarkRegistry | None = None,
        quality: QualityEvaluator | None = None,
        score_fn: Callable[[GenerationCandidate], float | None] | None = None,
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
        """留出评测：未注册基线 / 无留出分 ⇒ `freeze`（无法评测）；否则对比基线判退化。

        阈值口径：已注册的基线分**就是绝对阈值**（`held_out < baseline - margin` 即退化），
        `margin` 缺省 `0.0`（分毫不许退）—— 不新增第二阈值参数。
        """
        baseline = self._registry.baseline_of(candidate.target_plugin)
        if baseline is None:
            return self._frozen(baseline=0.0)
        held_out = self._held_out_score(candidate)
        if held_out is None:
            return self._frozen(baseline=baseline)
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

    @staticmethod
    def _frozen(*, baseline: float) -> EvalReport:
        """无法评测的结论：`held_out_score` **无意义**（记 `0.0`，不得读作「得分为 0」）。

        `baseline` 为未注册时的 `0.0` 同样无意义；消费者 SHALL 只认 `verdict`
        （见 evolution spec「留出评测」）。
        """
        return EvalReport(
            passed=False, held_out_score=0.0, baseline_score=baseline, verdict="freeze"
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

    def _held_out_score(self, candidate: GenerationCandidate) -> float | None:
        """留出分；**无打分器 ⇒ `None`**（无法评测 —— 不以常量 `0.0` 冒充分数）。"""
        if self._score_fn is not None:
            return self._score_fn(candidate)
        return None
