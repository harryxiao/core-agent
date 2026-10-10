"""进化冷路径的 trace 通路接线（change 0101）。

规格「执行循环」要求收尾按轮调用可选的 trace 完成回调、「经验采集」要求带模块归因的事件
被采为可归因证据。本文件证明组合根**真的**把主 loop 的收尾回调接到
`EvolutionWorker.on_trace_complete`（evolution 关闭时不接、不造空转闭包），并给出
「loop 失败 → 回调登记 → 冷路径采集 → 诊断归因到 loop.default」的端到端链路
（**离线替身，不出网**）。
"""

from __future__ import annotations

from typing import cast

import pytest

from core.configuration import ConfigManager
from core.evolution import (
    Diagnoser,
    Evaluator,
    EvolutionEngine,
    EvolutionWorker,
    Proposer,
    Trace,
    Validator,
)
from core.loop import Action, DefaultLoop
from core.memory import MemoryEntry
from core.observability import Tracer
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _write_config(tmp_path, *, evolution: bool = True) -> str:
    body = _LLM_SECTION
    if not evolution:
        body += "features:\n  evolution: false\n"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(body, encoding="utf-8")
    return str(cfg)


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _main_loop(runtime: object) -> DefaultLoop:
    return cast(DefaultLoop, runtime.loop)  # type: ignore[attr-defined]


def _engine() -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(), proposer=Proposer(), validator=Validator(), evaluator=Evaluator()
    )


# ---- 组合根装配 ----


def test_main_loop_wired_to_worker_trace_observer(api_key, tmp_path) -> None:
    """组合根把主 loop 的收尾回调接到 worker 的 trace 完成登记（不再恒空）。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    loop = _main_loop(runtime)

    assert loop._trace_observer is not None, "evolution 开启 ⇒ 必须接线"  # noqa: SLF001
    assert loop._trace_observer == runtime.evolution.on_trace_complete  # noqa: SLF001


def test_disabled_evolution_does_not_wire_trace_observer(api_key, tmp_path) -> None:
    """evolution 关闭 ⇒ 不注入（不为「未装配」造空转闭包，同 cold_path 口径）。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, evolution=False)))
    loop = _main_loop(runtime)

    assert runtime.evolution is None
    assert loop._trace_observer is None  # noqa: SLF001


# ---- 端到端链路（离线替身） ----


def test_loop_failure_flows_to_module_attribution() -> None:
    """loop 自身失败 → 回调登记 → 冷路径采集 → 诊断归因到 `loop.default`。"""
    tracer = Tracer()
    worker = EvolutionWorker(tracer=tracer, engine=_engine())
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        tracer=tracer,
        trace_observer=worker.on_trace_complete,
        max_rounds=0,
    )

    result = loop.run("任务")

    assert result.failed, "轮数上限 ⇒ 本轮失败"
    # change 0103：回调在封口**之前**取快照，故封口后 worker 仍持本轮事件
    assert len(worker._completed) == 1, "轮末回调已登记本轮快照"  # noqa: SLF001
    assert "loop_finished" in {e.kind for e in worker._completed[0]}  # noqa: SLF001
    outcome = worker.maybe_run(force=True)
    assert outcome is not None and outcome.candidate is not None
    assert outcome.candidate.target_plugin == "loop.default", "缺陷归因到执行循环模块"


def test_successful_loop_produces_no_defect_evidence() -> None:
    """正常收尾 → 无模块归因 → 冷路径无证据（不产虚假经验）。"""
    tracer = Tracer()
    worker = EvolutionWorker(tracer=tracer, engine=_engine())
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=tracer,
        trace_observer=worker.on_trace_complete,
    )

    loop.run("任务")
    outcome = worker.maybe_run()

    assert outcome is None, "无证据 ⇒ 冷路径不运行（阈值门与 run_cycle 均不触发）"


# ---- 记忆面 → 诊断面桥（change 0188 / ADR-0179 / 台账 E125） ----


def test_composition_root_wires_failure_lookup(api_key, tmp_path) -> None:
    """组合根注入失败摘要接缝：已沉淀的 `loop.failure.<id>` 经诊断器可取回并入报告。

    端到端（离线）：`runtime.memory` 写一条失败条目 ⇒ 接缝按 id 取正文 ⇒ `diagnose` 的报告
    `failure_notes` 含该摘要，而**归因判定**不变。未沉淀的 trace ⇒ `None`（不伪造证据）。
    """
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    runtime.memory.write(
        "L2",
        MemoryEntry(
            id="loop.failure.T1",
            layer="L2",
            content="失败：终止动作未达成",
            tags=["loop", "failure"],
            source="loop",
            trace_id="T1",
        ),
    )
    assert runtime.evolution is not None
    diagnoser = runtime.evolution.engine._diagnoser  # noqa: SLF001

    assert diagnoser._failure_lookup is not None, "组合根必须接线"  # noqa: SLF001
    assert diagnoser._failure_lookup("T1") == "失败：终止动作未达成"  # noqa: SLF001
    assert diagnoser._failure_lookup("未沉淀") is None  # noqa: SLF001

    report = diagnoser.diagnose(  # noqa: SLF001
        [
            Trace(
                trace_id="T1",
                task_type="loop",
                action={"event": "loop_finished"},
                result={"failed": True},
                success=False,
                plugin_id="loop.default",
            )
        ]
    )

    assert report.failure_notes == ["失败：终止动作未达成"]
    assert report.target_plugin == "loop.default", "归因判定不变（桥只增补证据面）"
