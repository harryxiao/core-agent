"""结晶通路：真实基准执行器注入 + 基准人工注册操作面（change 0212 / ADR-0202 / 台账 E149）。

规格「评测基建」要求：① 执行器由组合根注入（数据面 / 执行面分离）；② 执行器**缺省关**
（`features.evolution_benchmark_runner`）—— 注册基准 ≠ 同意烧模型调用；③ 提供 CLI 注册操作面
（只写数据面、不装配运行时）。本文件证明四件事：

- `_run_bench_sample` 的**执行语义**：会话隔离（`session_id="bench"`）、失败 ⇒ `None`、
  异常**冒泡**（不吞成 0 分）；
- **门控关（缺省）**：即便基准 + 基线都已落盘，留出评测仍判 `freeze`（与未引入执行面时**逐字
  一致** —— 不烧模型）；
- **门控开**：执行器注入 ⇒ 逐样本真实执行产出留出分，候选**不再** `freeze`；
- CLI `evolve benchmark {register|set-baseline|list}` 只写数据面、落盘跨进程可读。

全程离线（模型面为桩 provider，不出网）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.entry import main
from core.evolution import Benchmark, BenchmarkRegistry, Trace
from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from core.loop import LoopResult
from core.runtime import _run_bench_sample, build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)
_TARGET = "memory.retrieve"
_REPLY = "PASS"
# 合法技能内容（0236 门判据：task_types 非空 + instructions 非空 + param_schema 为 dict）
_SKILL_CONTENT_JSON = json.dumps(
    {"task_types": ["module_health"], "instructions": "失败先查模块健康。", "param_schema": {}}
)
_BASELINE = 0.7


def _write_config(tmp_path: Path, *, runner: bool = False) -> str:
    body = _LLM_SECTION
    if runner:
        body += "features:\n  evolution_benchmark_runner: true\n"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(body, encoding="utf-8")
    return str(cfg)


class _StubProvider(LLMProvider):
    """替代 `StdlibLLMProvider` 的桩：构造签名兼容组合根调用点，调用期不出网。

    流式路径（loop 的 planner 走 `astream`）产出 `_REPLY` 的自然语言回复 ⇒ 该轮成功、
    `LoopResult.reply == _REPLY`。
    """

    def __init__(self, **_kwargs: Any) -> None: ...

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        # 0236 后冷路径多一类模型请求：技能内容蒸馏（prompt 头含「技能内容蒸馏器」）。
        # 桩按 prompt 分派 —— 该请求回合法 SkillContent JSON，其余照旧回 `_REPLY`
        # （PASS）。不分派则 writer `json.loads("PASS")` 失败 ⇒ 空壳门拒 ⇒ eval 恒 None。
        prompt = "".join(getattr(m, "content", "") for m in request.messages)
        content = _SKILL_CONTENT_JSON if "技能内容蒸馏器" in prompt else _REPLY
        return LLMResponse(
            content=content,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest):
        yield LLMChunk(content=_REPLY)

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


class _GateOutcome:
    """门禁结果替身（消费侧只要求 `passed`）。"""

    passed = True
    reason = ""


def _stub_gate_executor(**_kwargs: Any) -> Any:
    """门禁执行器工厂替身：结晶面两道门一律通过（隔离子进程门禁，本文件只考评测面）。"""

    def _run(_gate: Any) -> _GateOutcome:
        return _GateOutcome()

    return _run


def _trace() -> Trace:
    """一条失败且带结果的 trace（缺结果者被采集器视作无证据，不进诊断）。"""
    return Trace(
        trace_id="1",
        task_type="t",
        action={"a": 1},
        result="err",
        success=False,
        plugin_id=_TARGET,
    )


def _seed_benchmark() -> None:
    """把一份**绑定 `_TARGET` 且含样本**的基准 + 基线写进组合根同源的单文件落盘。"""
    path = _benchmark_path()
    registry = BenchmarkRegistry(path=path)
    registry.register(
        Benchmark(
            benchmark_id="b1",
            task_type="module_health",
            samples=[{"input": "任意任务", "expected": _REPLY}],
            plugin_id=_TARGET,
        )
    )
    registry.set_baseline(_TARGET, 0.5)


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """组合根构造的 provider 与门禁执行器换成替身：装配与评测全程不出网、不跑真门。"""
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _StubProvider)
    monkeypatch.setattr("core.runtime.build_gate_executor", _stub_gate_executor)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


# ---- 1. 执行语义（`_run_bench_sample`） ----


class _FakeLoop:
    """最小 loop 替身：记录被调用参数，按需返回失败结果 / 抛异常。"""

    def __init__(self, *, failed: bool = False, boom: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self._failed = failed
        self._boom = boom

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        self.calls.append((user_input, session_id))
        if self._boom:
            raise RuntimeError("端点不可达")
        return LoopResult(reply=_REPLY, trace_id="t", failed=self._failed)


def test_run_bench_sample_executes_isolated_session() -> None:
    """成功样本：以 `session_id="bench"` 跑一轮，返回回复正文（供 scorer 与 expected 比对）。"""
    loop = _FakeLoop()

    assert _run_bench_sample(loop, {"input": "任务"}) == _REPLY  # type: ignore[arg-type]
    assert loop.calls == [("任务", "bench")], "会话隔离：样本不污染全局记忆层"


def test_run_bench_sample_returns_none_on_failure() -> None:
    """轮失败 ⇒ `None`（scorer 语义：无产出 ⇒ 完成度 0），不把失败谎报成回复。"""
    assert _run_bench_sample(_FakeLoop(failed=True), {"input": "任务"}) is None  # type: ignore[arg-type]


def test_run_bench_sample_bubbles_exception() -> None:
    """执行器异常**冒泡**（评测器据此判 freeze）—— 不吞成 0 分、不吞成通过。"""
    with pytest.raises(RuntimeError, match="端点不可达"):
        _run_bench_sample(_FakeLoop(boom=True), {"input": "任务"})  # type: ignore[arg-type]


# ---- 2. 门控关（缺省）：注册了基准也不烧模型，仍 `freeze` ----


def test_gate_off_does_not_inject_runner(offline, tmp_path: Path) -> None:
    """缺省关 ⇒ 组合根**不注入**执行器（与未引入本执行面时逐字一致）。"""
    _seed_benchmark()
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    assert runtime.evolution is not None
    scorer = runtime.evolution.engine._evaluator._score_fn  # noqa: SLF001
    assert scorer._runners == {}  # noqa: SLF001


def test_gate_off_still_freezes_despite_registered_benchmark(offline, tmp_path: Path) -> None:
    """门控关：基准 + 基线都落盘，仍判 `freeze`（注册基准**不是**同意执行）。"""
    _seed_benchmark()
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    assert runtime.evolution is not None

    outcome = runtime.evolution.engine.run_cycle([_trace()])

    assert outcome.status == "frozen"
    assert outcome.eval is not None and outcome.eval.verdict == "freeze"


# ---- 3. 门控开：真实执行产出留出分，不再 freeze ----


def test_gate_on_injects_runner_for_produced_task_types(offline, tmp_path: Path) -> None:
    """门控开 ⇒ 为 worker 生产产出的两个 `task_type` 注入执行器。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, runner=True)))
    assert runtime.evolution is not None
    scorer = runtime.evolution.engine._evaluator._score_fn  # noqa: SLF001

    assert set(scorer._runners) == {"module_health", "tool_use"}  # noqa: SLF001


def test_gate_on_produces_held_out_score(offline, tmp_path: Path) -> None:
    """门控开：逐样本真实执行（子 Agent 形状）⇒ 留出分 = 1.0，候选不再 `freeze`。"""
    _seed_benchmark()
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, runner=True)))
    assert runtime.evolution is not None

    outcome = runtime.evolution.engine.run_cycle([_trace()])

    assert outcome.eval is not None
    assert outcome.eval.verdict == "publish", "真实执行产出留出分 ⇒ 不再 freeze"
    assert outcome.eval.held_out_score == 1.0, "回复与 expected 逐字相等 ⇒ 满分（非常量缺省值）"
    assert outcome.status == "pending", "过门 + 不退化 ⇒ 进人工确认队列（不绕过确认自动发布）"


# ---- 4. CLI 注册操作面（数据面免 runtime） ----


def _samples_file(tmp_path: Path) -> Path:
    path = tmp_path / "samples.json"
    path.write_text(json.dumps([{"input": "任务", "expected": _REPLY}]), encoding="utf-8")
    return path


def _benchmark_path() -> Path:
    return Path(os.environ["CORE_STATE_DIR"]) / "evolution-benchmarks.json"


def test_cli_register_set_baseline_then_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`evolve benchmark register|set-baseline|list`：只写数据面、落盘、清单可见。"""
    cfg = _write_config(tmp_path)
    samples = _samples_file(tmp_path)

    assert (
        main(
            [
                "--config",
                cfg,
                "evolve",
                "benchmark",
                "register",
                "b1",
                "--plugin-id",
                _TARGET,
                "--task-type",
                "module_health",
                "--samples",
                str(samples),
            ]
        )
        == 0
    )
    assert main(["--config", cfg, "evolve", "benchmark", "set-baseline", _TARGET, "0.7"]) == 0
    capsys.readouterr()
    assert main(["--config", cfg, "evolve", "benchmark", "list"]) == 0

    out = capsys.readouterr().out
    assert "b1" in out and _TARGET in out and "0.7" in out

    # 跨进程可读（新构造的注册表读回同一份数据）
    registry = BenchmarkRegistry(path=_benchmark_path())
    assert registry.benchmark_for_plugin(_TARGET) is not None
    assert registry.baseline_of(_TARGET) == _BASELINE


def test_cli_register_requires_plugin_id(tmp_path: Path) -> None:
    """`--plugin-id` 必填：未绑定目标的基准不激活任何评测（`benchmark_for_plugin` 永不命中）。"""
    cfg = _write_config(tmp_path)
    samples = _samples_file(tmp_path)

    with pytest.raises(SystemExit):
        main(
            [
                "--config",
                cfg,
                "evolve",
                "benchmark",
                "register",
                "b1",
                "--task-type",
                "module_health",
                "--samples",
                str(samples),
            ]
        )


def test_cli_list_on_missing_file_is_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """落盘缺失 ⇒ 空基准集（不阻断、不抛）。"""
    assert main(["--config", _write_config(tmp_path), "evolve", "benchmark", "list"]) == 0
    assert "b1" not in capsys.readouterr().out
