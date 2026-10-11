"""Phase 15 验证门 + 结晶验收测试（M10 后半段）。

覆盖：评测基建 list、真实缺陷全链路结晶闭环（skill / plugin 双路径）、
沙箱三域隔离 + 资源配额、HITL 三动作分级路由、崩溃恢复 / 时间旅行接 loop。
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator

import pytest

from core.configuration import ConfigManager
from core.durability import CrashRecovery, TimeTravel
from core.evolution import (
    Benchmark,
    BenchmarkRegistry,
    Diagnoser,
    Evaluator,
    EvolutionEngine,
    Proposer,
    Trace,
    Validator,
)
from core.loop import LoopEvent, LoopResult, collect_result
from core.memory import Crystallizer
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    Plan,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    SubtaskOutcome,
    TaskScheduler,
)
from core.permission import (
    AccessControlError,
    ApprovalRequest,
    ApprovalWorkflow,
    PermissionErrorCode,
    ResourceBudget,
    SandboxDomain,
    SandboxManager,
    SandboxPolicy,
)
from core.plugin_registry import Effect
from core.runtime import build_runtime
from core.skills import SkillLibrary


def _trace(trace_id: str, *, success: bool, plugin_id: str | None = None) -> Trace:
    return Trace(
        trace_id=trace_id,
        task_type="tool_use",
        action={"tool": plugin_id, "args": {}},
        result={"ok": success},
        success=success,
        plugin_id=plugin_id,
    )


def _request() -> ApprovalRequest:
    return ApprovalRequest(
        op="delete",
        target="/prod/db",
        impact_summary="删库",
        rollback_plan="备份恢复",
        trace_id="t1",
    )


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


class _FakeLoop:
    """最小 LoopPlugin 替身：astream 产固定终态、记录调用目标（携带 trace_id）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self.calls.append(user_input)
        yield LoopEvent("loop_finished", LoopResult(reply="ok", trace_id="fake-trace"))

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        return await collect_result(self.astream(user_input, session_id=session_id))


class _SpyCrystallizer(Crystallizer):
    """记录 crystallize 调用的 Crystallizer 替身。"""

    def __init__(self) -> None:
        super().__init__()
        self.crystallized: list[str] = []

    def crystallize(self, skill_entry):
        self.crystallized.append(skill_entry.id)
        return super().crystallize(skill_entry)


class _PluginProposer(Proposer):
    """把候选 kind 改为 plugin，以走 MemoryCrystallizer 结晶路径。"""

    def propose(self, diagnosis):
        candidate = super().propose(diagnosis)
        candidate.kind = "plugin"
        return candidate


# ---- 评测基建 ----


def test_benchmark_registry_list() -> None:
    registry = BenchmarkRegistry()
    benchmark = Benchmark(
        benchmark_id="b1", task_type="retrieval", samples=[{"input": "x", "expected": "y"}]
    )
    registry.register(benchmark)
    assert registry.list() == [benchmark]


# ---- 真实缺陷全链路 ----


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


def test_full_chain_real_defect_published() -> None:
    """工具写错路径的缺陷走完 诊断→提案→验证门→留出评测→结晶 → published。"""
    library = SkillLibrary()
    engine = EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=_passing_validator(),
        evaluator=_passing_evaluator(),
        library=library,
        memory_crystallizer=Crystallizer(),
    )
    outcome = engine.run_cycle([_trace("1", success=False, plugin_id="tools.file_write")])
    assert outcome.status == "pending"
    assert outcome.diagnosis is not None
    assert outcome.diagnosis.target_plugin == "tools.file_write"
    assert outcome.candidate is not None
    assert library.all_skills() == []  # 未确认前不发布

    engine.confirm(outcome.candidate)
    result = engine.crystallize(outcome.candidate)
    assert result.status == "published"
    assert result.skill_id == "skills.evolution.tools.file_write"
    assert library.lookup(result.skill_id) is not None


def test_plugin_candidate_crystallizes_accepted() -> None:
    """plugin 候选走 MemoryCrystallizer 结晶：accepted（无产物发布）且无 skill_id。"""
    crystallizer = _SpyCrystallizer()
    engine = EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=_PluginProposer(),
        validator=_passing_validator(),
        evaluator=_passing_evaluator(),
        memory_crystallizer=crystallizer,
    )
    outcome = engine.run_cycle([_trace("1", success=False, plugin_id="memory.retrieve")])
    assert outcome.status == "pending"
    assert outcome.candidate is not None and outcome.candidate.kind == "plugin"

    engine.confirm(outcome.candidate)
    result = engine.crystallize(outcome.candidate)
    assert result.status == "accepted"
    assert result.skill_id is None
    assert crystallizer.crystallized  # crystallizer 被调用


# ---- 沙箱三域 + 资源配额 ----


def test_sandbox_three_domains() -> None:
    policy = SandboxPolicy(host_allowlist=["api.example.com"], fs_allowlist={"/data": "rw"})
    manager = SandboxManager(policy=policy)

    browser = manager.run(["api.example.com"], domain=SandboxDomain.BROWSER)
    assert browser.exit_code == 0
    with pytest.raises(AccessControlError) as exc_info:
        manager.run(["evil.com"], domain=SandboxDomain.BROWSER)
    assert exc_info.value.code is PermissionErrorCode.PERMISSION_DENIED

    fs = manager.run(["/data", "w"], domain=SandboxDomain.FILESYSTEM)
    assert fs.exit_code == 0
    with pytest.raises(AccessControlError):
        manager.run(["/etc/passwd"], domain=SandboxDomain.FILESYSTEM)


def test_sandbox_cpu_quota_exceeded() -> None:
    manager = SandboxManager()
    budget = ResourceBudget(max_cpu_seconds=1)
    with pytest.raises(AccessControlError) as exc_info:
        manager.run([sys.executable, "-c", "while True: pass"], budget=budget)
    assert exc_info.value.code is PermissionErrorCode.QUOTA_EXCEEDED


# ---- HITL 三动作 ----


def test_hitl_approve_reject_edit_plan() -> None:
    workflow = ApprovalWorkflow()

    approved = workflow.create(_request())
    result = workflow.approve(approved)
    assert result.approved is True
    assert approved.status == "approved"

    rejected = workflow.create(_request())
    workflow.reject(rejected, note="不安全")
    assert rejected.status == "rejected"

    edited = workflow.create(_request())
    new_ticket = workflow.edit_plan(edited, _request(), note="改目标")
    assert edited.status == "superseded"
    assert new_ticket.status == "pending"
    assert new_ticket is not edited
    assert edited in workflow.list_archived()


# ---- 崩溃恢复 / 时间旅行接 loop ----


def test_runtime_wires_durability_components(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    assert isinstance(runtime.time_travel, TimeTravel)
    assert isinstance(runtime.crash_recovery, CrashRecovery)
    assert runtime.recover() == []  # 无检查点 → 无恢复


def test_runtime_shared_effect_tracker_rollback(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    # ToolProvider / MemoryStore / TimeTravel 共享同一 EffectTracker
    assert runtime.tools._tracker is runtime.time_travel._effect_tracker
    assert runtime.memory._tracker is runtime.time_travel._effect_tracker

    # 记录 loop 内可逆副作用 → 写含 trace_ids 的检查点 → 时间旅行回滚
    undone: list[str] = []
    runtime.time_travel._effect_tracker.record(
        Effect(
            op="write",
            target="f.txt",
            undo=lambda: undone.append("f.txt"),
            reversible=True,
            coeffect=["filesystem:write"],
            trace_id="t1",
            ts=0.0,
        )
    )
    checkpoint = runtime.checkpoints.create_checkpoint("task1", "default", {"trace_ids": ["t1"]})
    runtime.time_travel.rollback(checkpoint.checkpoint_id)
    assert undone == ["f.txt"]


def test_runtime_recover_restores_incomplete_skips_done(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    runtime.checkpoints.create_checkpoint("done-task", "default", {"done": True})
    todo = runtime.checkpoints.create_checkpoint("todo-task", "default", {"done": False})

    handles = runtime.recover()
    assert len(handles) == 1
    assert handles[0].checkpoint_id == todo.checkpoint_id


def test_runtime_checkpoint_carries_initiating_session(monkeypatch, tmp_path) -> None:
    """组合根检查点闭包写**实参原值**会话标识（change 0190：去 `"default"` 占位）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    plan = Plan(
        subtasks=[Subtask(id="1", goal="g", acceptance="")],
        goal="g",
        order=["1"],
        waves=[["1"]],
    )

    runtime.orchestrator._checkpoint("task-s", [], plan, "sess-real")

    cps = runtime.checkpoints.list_checkpoints(task_id="task-s")
    assert len(cps) == 1
    assert cps[-1].session_id == "sess-real"  # 真值入元数据（非占位 "default"）


# ---- TaskScheduler trace_id + on_done ----


def test_scheduler_on_done_and_trace_id() -> None:
    main = _FakeLoop()
    done: list[tuple[str, list[SubtaskOutcome]]] = []

    def planner(goal: str) -> list[Subtask]:
        return [Subtask(id="1", goal="run the default task", acceptance="")]

    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(
            [AgentProfile(agent_id="main", capabilities=["default"], loop=main)]
        ),
        state_machine=StateMachine(),
        on_done=lambda task_id, outcomes, plan, session_id: done.append((task_id, outcomes)),
    )

    outcomes = asyncio.run(scheduler.run("task-1", "plan"))

    assert done == [("task-1", outcomes)]
    assert outcomes[0].trace_id == "fake-trace"
