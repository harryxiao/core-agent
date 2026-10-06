"""结晶面门的数据面：基准集落盘 + 真实留出评测 + 口径版本（change 0119 / phase-31 切片 1）。

phase-31 G4 + G3：生产装配的 `Evaluator()` 无参 ⇒ 留出分恒 `0.0`、基线恒 `0.0` ⇒ **恒 publish**
（门的第 4 阶段产出恒为常量）。本文件证明三件事：① 基准集与基线**落盘可跨进程读**；② 留出分由
**基准样本经执行器真实执行**产出，**无法评测**（无绑定基准 / 无样本 / 无执行器 / 无基线）时
fail-closed 判 `freeze`（**不谎报** `rollback`、不放行 `publish`）；③ 旧口径候选不得投放（G5 锚点：
`frozen` / `rollback` 两分支可达）。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.evolution import (
    GATE_CALIBER,
    Benchmark,
    BenchmarkRegistry,
    BenchmarkScorer,
    Diagnoser,
    DiagnosisReport,
    Evaluator,
    EvolutionEngine,
    EvolutionError,
    EvolutionErrorCode,
    GenerationCandidate,
    PendingQueue,
    Proposer,
    Trace,
    Validator,
)
from core.runtime import build_runtime

# ---- 夹具 ----


def _benchmark(
    benchmark_id: str = "bm.retrieve",
    *,
    task_type: str = "t",
    plugin_id: str | None = "memory.retrieve",
    samples: list[dict[str, Any]] | None = None,
) -> Benchmark:
    return Benchmark(
        benchmark_id=benchmark_id,
        task_type=task_type,
        plugin_id=plugin_id,
        samples=samples
        if samples is not None
        else [
            {"input": "a", "expected": "A"},
            {"input": "b", "expected": "B"},
        ],
    )


def _exact_runner(sample: dict[str, Any]) -> Any:
    """基准执行器替身：正确答案（`input` 大写）。"""
    return str(sample["input"]).upper()


def _wrong_runner(_sample: dict[str, Any]) -> Any:
    return "wrong"


def _candidate() -> GenerationCandidate:
    return Proposer().propose(DiagnosisReport(target_plugin="memory.retrieve", issue="检索失败"))


def _trace(trace_id: str = "1", *, plugin_id: str = "memory.retrieve") -> Trace:
    """一条**失败且带结果**的 trace（缺结果者被采集器视作无证据，不进诊断）。"""
    return Trace(
        trace_id=trace_id,
        task_type="t",
        action={"a": 1},
        result="err",
        success=False,
        plugin_id=plugin_id,
    )


def _engine(evaluator: Evaluator) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(), proposer=Proposer(), validator=Validator(), evaluator=evaluator
    )


# ---- 1. 基准集与基线：落盘、跨进程可读、损坏降级告警 ----


def test_registry_persists_across_instances(tmp_path: Any) -> None:
    """注册 + 设基线 ⇒ 落盘；新实例（同 path）读回同一份（跨进程可读）。"""
    path = tmp_path / "evolution-benchmarks.json"
    registry = BenchmarkRegistry(path=path)
    registry.register(_benchmark())
    registry.set_baseline("memory.retrieve", 0.8)

    reloaded = BenchmarkRegistry(path=path)
    assert [b.benchmark_id for b in reloaded.list()] == ["bm.retrieve"]
    assert reloaded.baseline_of("memory.retrieve") == pytest.approx(0.8)
    assert reloaded.benchmark_for_plugin("memory.retrieve") is not None


def test_registry_without_path_stays_in_memory() -> None:
    """未注入路径：纯内存（既有调用方零行为变化）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    assert registry.baseline_of("memory.retrieve") is None
    assert registry.baseline_score("memory.retrieve") == 0.0


def test_registry_corrupt_file_degrades_with_warning(tmp_path: Any) -> None:
    """损坏 / 结构不符 ⇒ 降级为空基准集 + 告警（不抛、不阻断启动）。"""
    path = tmp_path / "evolution-benchmarks.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.warns(UserWarning):
        registry = BenchmarkRegistry(path=path)
    assert registry.list() == []

    path.write_text(json.dumps({"benchmarks": "nope"}), encoding="utf-8")
    with pytest.warns(UserWarning):
        assert BenchmarkRegistry(path=path).list() == []


def test_registry_missing_file_is_silent(tmp_path: Any) -> None:
    """落盘缺失 ⇒ 空基准集，**不**告警（与「损坏」区分开）。"""
    registry = BenchmarkRegistry(path=tmp_path / "absent.json")
    assert registry.list() == []


def test_benchmark_binds_to_plugin() -> None:
    """候选↔基准按 `plugin_id` 绑定（不回落任意基准）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark(plugin_id="memory.retrieve"))
    assert registry.benchmark_for_plugin("memory.retrieve") is not None
    assert registry.benchmark_for_plugin("web.fetch") is None


# ---- 2. 真实打分：逐样本执行 → 聚合 ----


def test_scorer_scores_samples_by_real_execution() -> None:
    """留出分 = 逐样本**真实执行**结果与期望对比后的聚合（全对 ⇒ 1.0）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    scorer = BenchmarkScorer(registry, runners={"t": _exact_runner})
    candidate = _candidate()
    assert scorer(candidate) == pytest.approx(1.0)


def test_scorer_partial_match_scores_between() -> None:
    """执行器产出与期望不符 ⇒ 正确性维度失分，聚合分落在中间。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    scorer = BenchmarkScorer(registry, runners={"t": _wrong_runner})
    score = scorer(_candidate())
    assert score is not None
    assert 0.0 < score < 1.0


def test_scorer_returns_none_when_unable_to_evaluate() -> None:
    """无绑定基准 / 无样本 / 无执行器 ⇒ `None`（无法评测，不产出分数）。"""
    candidate = _candidate()
    unbound = BenchmarkRegistry()
    unbound.register(_benchmark(plugin_id="web.fetch"))
    assert BenchmarkScorer(unbound, runners={"t": _exact_runner})(candidate) is None

    empty = BenchmarkRegistry()
    empty.register(_benchmark(samples=[]))
    assert BenchmarkScorer(empty, runners={"t": _exact_runner})(candidate) is None

    no_runner = BenchmarkRegistry()
    no_runner.register(_benchmark())
    assert BenchmarkScorer(no_runner)(candidate) is None
    assert BenchmarkScorer(no_runner, runners={"other": _exact_runner})(candidate) is None


def test_scorer_propagates_runner_errors() -> None:
    """执行器抛异常 ⇒ 冒泡（不吞成 0 分、不吞成通过）。"""

    def _boom(_sample: dict[str, Any]) -> Any:
        raise RuntimeError("执行器炸了")

    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    with pytest.raises(RuntimeError):
        BenchmarkScorer(registry, runners={"t": _boom})(_candidate())


# ---- 3. Evaluator 三态：publish / rollback / freeze ----


def test_evaluator_freezes_when_score_unavailable() -> None:
    """无法评测 ⇒ `verdict=freeze`、`passed=False`（不报 publish、不谎报 rollback）。"""
    report = Evaluator(score_fn=lambda _c: None).evaluate(_candidate())
    assert report.verdict == "freeze"
    assert report.passed is False


def test_evaluator_freezes_without_baseline() -> None:
    """有基准 + 有执行器但**未注册基线** ⇒ 无对比面 ⇒ 无法评测（不静默按 0.0 放行）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    evaluator = Evaluator(
        registry=registry, score_fn=BenchmarkScorer(registry, runners={"t": _exact_runner})
    )
    report = evaluator.evaluate(_candidate())
    assert report.verdict == "freeze"
    assert report.passed is False


def test_evaluator_rollback_still_reachable() -> None:
    """退化仍可判 `rollback`（真实打分低于基线；G5 锚点之一）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    registry.set_baseline("memory.retrieve", 0.9)
    evaluator = Evaluator(
        registry=registry, score_fn=BenchmarkScorer(registry, runners={"t": _wrong_runner})
    )
    report = evaluator.evaluate(_candidate())
    assert report.verdict == "rollback"
    assert report.held_out_score < report.baseline_score


def test_evaluator_publishes_when_not_regressed() -> None:
    """真实打分不低于基线 ⇒ `publish`（三态齐全，非「恒常量」）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    registry.set_baseline("memory.retrieve", 0.9)
    evaluator = Evaluator(
        registry=registry, score_fn=BenchmarkScorer(registry, runners={"t": _exact_runner})
    )
    report = evaluator.evaluate(_candidate())
    assert report.verdict == "publish"
    assert report.passed is True


# ---- 4. 端到端：生产形状装配下的结局（G5 锚点） ----


def test_run_cycle_freezes_in_production_shape(tmp_path: Any) -> None:
    """生产形状（落盘 registry + 打分器，**未接执行器**）⇒ `status="frozen"`（不是 rollback）。"""
    registry = BenchmarkRegistry(path=tmp_path / "evolution-benchmarks.json")
    engine = _engine(Evaluator(registry=registry, score_fn=BenchmarkScorer(registry)))
    outcome = engine.run_cycle([_trace()])
    assert outcome.status == "frozen"
    assert outcome.eval is not None and outcome.eval.verdict == "freeze"
    assert outcome.candidate is not None


def test_run_cycle_rollbacks_with_registered_benchmark() -> None:
    """注册基准 + 基线 + 执行器（打分低于基线）⇒ `status="rollback"`（G5 锚点之二）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    registry.set_baseline("memory.retrieve", 0.9)
    engine = _engine(
        Evaluator(
            registry=registry, score_fn=BenchmarkScorer(registry, runners={"t": _wrong_runner})
        )
    )
    outcome = engine.run_cycle([_trace()])
    assert outcome.status == "rollback"
    assert outcome.eval is not None and outcome.eval.verdict == "rollback"


# ---- 5. 口径版本：旧口径候选不得投放 ----


def test_crystallize_rejects_stale_caliber() -> None:
    """旧口径候选（含落盘旧行）⇒ 结构化拒绝、**不发布**；理由不得记为「退化」。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    registry.set_baseline("memory.retrieve", 0.9)
    engine = _engine(
        Evaluator(
            registry=registry, score_fn=BenchmarkScorer(registry, runners={"t": _exact_runner})
        )
    )
    outcome = engine.run_cycle([_trace()])
    candidate = outcome.candidate
    assert candidate is not None

    candidate.caliber = 0  # 模拟旧口径（落盘早于口径字段引入）
    engine.confirm(candidate)
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(candidate)
    assert exc_info.value.code is EvolutionErrorCode.GATE_CALIBER_STALE
    assert "退化" not in exc_info.value.message


def test_crystallize_allows_current_caliber() -> None:
    """现口径候选：口径校验不阻断（正常结晶）。"""
    registry = BenchmarkRegistry()
    registry.register(_benchmark())
    registry.set_baseline("memory.retrieve", 0.9)
    engine = _engine(
        Evaluator(
            registry=registry, score_fn=BenchmarkScorer(registry, runners={"t": _exact_runner})
        )
    )
    outcome = engine.run_cycle([_trace()])
    candidate = outcome.candidate
    assert candidate is not None and candidate.caliber == GATE_CALIBER
    engine.confirm(candidate)
    assert engine.crystallize(candidate).status == "published"


def test_caliber_persists_with_pending_queue(tmp_path: Any) -> None:
    """口径随候选台账落盘；落盘**旧行**（无该字段）解析为 0（旧口径）。"""
    path = tmp_path / "evolution-pending.json"
    queue = PendingQueue(path=path)
    queue.record(_candidate())
    reloaded = PendingQueue(path=path)
    assert reloaded.records()[0].candidate.caliber == GATE_CALIBER

    payload = json.loads(path.read_text(encoding="utf-8"))
    for record in payload["records"]:
        record.pop("caliber")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert PendingQueue(path=path).records()[0].candidate.caliber == 0


# ---- 6. 组合根装配：产线的评估器不再是「无参裸桩」 ----


def test_runtime_evaluator_is_a_real_gate(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """生产装配：`build_runtime` 的引擎在**未注册任何基准**时判 `frozen`（真门，非恒通过桩）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    runtime = build_runtime(ConfigManager(yaml_path=str(cfg)))
    assert runtime.evolution is not None
    outcome = runtime.evolution.engine.run_cycle([_trace()])
    assert outcome.status == "frozen"
