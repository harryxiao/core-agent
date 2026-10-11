"""Phase 14 冷路径 + 长任务测试（M10 前半段）。

覆盖三条链路：① EvolutionWorker 消费 Tracer 轨迹 → 进化引擎 dry-run
（无轨迹 no_evidence / 成功轨迹 manual / 失败轨迹归因 pending）；②
TaskScheduler 多 Agent 编排真 DefaultLoop + checkpoint 每波次回调一次；
③ runtime 组合根装配 evolution / orchestrator / checkpoints 三组件。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from core.configuration import ConfigManager
from core.durability import CheckpointManager
from core.evolution import (
    BenchmarkRegistry,
    Diagnoser,
    Evaluator,
    EvolutionEngine,
    EvolutionWorker,
    Proposer,
    Validator,
)
from core.loop import LoopEvent, LoopResult, collect_result
from core.observability import TraceLogger, Tracer
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    SubtaskOutcome,
    TaskHandoff,
    TaskScheduler,
)
from core.runtime import build_runtime


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    return str(cfg)


class _RegisteredBaselines(BenchmarkRegistry):
    """测试替身：数据面上任意目标都视为已注册基线 0.5（判定面仍是真 `Evaluator`）。"""

    def baseline_of(self, _plugin_id: str) -> float | None:
        return 0.5


def _passing_evaluator() -> Evaluator:
    """过门评测器：基线可比（0.5）+ 留出分 0.9 ⇒ 真实地判 publish（0119 起无参裸桩不再恒通过）。"""
    return Evaluator(registry=_RegisteredBaselines(), score_fn=lambda _c: 0.9)


def _passing_validator() -> Validator:
    """过门验证门：review 与运行时测试都判过（0120 起无参 `Validator()` 不再恒通过 = 不得放行）。"""
    return Validator(review=lambda _c: True, tests=lambda _c: {"lint": True, "test": True})


def _engine() -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=_passing_validator(),
        evaluator=_passing_evaluator(),
    )


class _FakeLoop:
    """最小 LoopPlugin 替身：astream 产固定终态、记录调用目标（arun 供 handoff 路径）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self.calls.append(user_input)
        yield LoopEvent("loop_finished", LoopResult(reply="ok", trace_id="fake-trace"))

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        return await collect_result(self.astream(user_input, session_id=session_id))


# ---- ① EvolutionWorker 消费 Tracer 轨迹 ----


def test_worker_no_traces_returns_no_evidence() -> None:
    worker = EvolutionWorker(tracer=Tracer(), engine=_engine())

    outcome = worker.maybe_run(force=True)

    assert outcome is not None
    assert outcome.status == "no_evidence"


def test_worker_consumes_successful_trace() -> None:
    tracer = Tracer()
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("t1")
    logger.log_tool_call(trace_id, "tools.file_read", {"path": "x"}, {"ok": True}, 1.0)

    worker = EvolutionWorker(tracer=tracer, engine=_engine())
    worker.on_trace_complete(trace_id)
    outcome = worker.maybe_run(force=True)

    assert outcome is not None
    assert outcome.status == "manual"  # 无失败证据 → 无法归因 → manual
    assert outcome.diagnosis is not None
    assert outcome.diagnosis.target_plugin is None


def test_worker_failure_trace_diagnoses_plugin() -> None:
    tracer = Tracer()
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("t1")
    logger.log_tool_call(trace_id, "tools.file_read", {"path": "x"}, {"ok": False}, 1.0)

    worker = EvolutionWorker(tracer=tracer, engine=_engine())
    worker.on_trace_complete(trace_id)
    outcome = worker.maybe_run(force=True)

    assert outcome is not None
    assert outcome.status == "pending"  # 过验证门 + 留出评测 publish → 人工确认队列
    assert outcome.diagnosis is not None
    assert outcome.diagnosis.target_plugin == "tools.file_read"
    assert outcome.candidate is not None
    assert outcome.candidate.target_plugin == "tools.file_read"


# ---- ② TaskScheduler 多 Agent 编排 + checkpoint ----


def test_task_scheduler_multi_agent_checkpoint_per_wave() -> None:
    """两 Agent（default/code）+ 两波次：按能力路由到不同 Agent，checkpoint 每波次一次。"""
    main = _FakeLoop()
    coder = _FakeLoop()
    calls: list[tuple[str, list[str]]] = []

    def planner(goal: str) -> list[Subtask]:
        return [
            Subtask(id="1", goal="run the default task", acceptance=""),
            Subtask(id="2", goal="write the code", acceptance="", depends_on=["1"]),
        ]

    def checkpoint(
        task_id: str, outcomes: list[SubtaskOutcome], plan: object, session_id: str
    ) -> None:
        calls.append((task_id, [o.subtask_id for o in outcomes]))

    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(
            [
                AgentProfile(agent_id="main", capabilities=["default"], loop=main),
                AgentProfile(agent_id="coder", capabilities=["code"], loop=coder),
            ]
        ),
        state_machine=StateMachine(),
        checkpoint=checkpoint,
    )

    outcomes = asyncio.run(scheduler.run("task-1", "plan"))

    assert [o.ok for o in outcomes] == [True, True]
    assert calls == [("task-1", ["1"]), ("task-1", ["1", "2"])]  # 检查点携带累计结果
    assert main.calls == ["run the default task"]
    # 依赖结果交接：上游验收通过结果注入后继子任务输入（spec：依赖结果交接）
    assert coder.calls == [
        "write the code\n\n前置子任务结果（可直接引用）：\n"
        "[前置子任务 1] run the default task\n结果：ok"
    ]


def test_router_handoff_delegates_to_target_agent() -> None:
    main = _FakeLoop()
    router = MultiAgentRouter([AgentProfile(agent_id="main", capabilities=["default"], loop=main)])

    result = asyncio.run(router.handoff("main", TaskHandoff(task="do it")))

    assert result.reply == "ok"
    assert main.calls == ["do it"]


# ---- ③ runtime 组合根装配 ----


def test_build_runtime_wires_evolution_and_orchestration(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert isinstance(runtime.evolution, EvolutionWorker)
    assert isinstance(runtime.orchestrator, TaskScheduler)
    assert isinstance(runtime.checkpoints, CheckpointManager)
