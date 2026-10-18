"""未完成任务自动续跑（change 0278 / ADR-0268 / 台账 E214）。

规格锚点：`orchestration`「未完成任务自动续跑」、`configuration`「编排调度配置」（新键）、
`durability`「崩溃恢复」（显式 opt-in 例外）。本文件锁五件事：

- `orchestration.auto_resume` 三面齐备、默认 `false`、非法值阻断启动；
- 跨进程有界退避状态：首试即到期、60s 起指数退避、3 次耗尽后不再自动尝试、成功清零；
- 状态文件损坏容忍（告警后按空状态处理）；
- `_task_resumes` 从检查点重建 plan/completed/results/session，跳过 done / `turn.` / 坏计划，
  且取**时间戳最新**的可读快照；
- `task --resume-all` 显式执行、自动续跑在新任务之前、默认关时不执行。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.durability import Checkpoint, CheckpointManager, CheckpointStore, Snapshot
from core.entry import main
from core.loop import LoopEvent
from core.orchestration import Plan, Subtask, TaskResume, plan_to_dict
from core.orchestration.auto_resume import (
    AUTO_RESUME_MAX_ATTEMPTS,
    AutoResumeState,
)
from core.runtime import _task_resumes

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _manager(tmp_path: Path, extra: str = "") -> ConfigManager:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    manager = ConfigManager(yaml_path=cfg, environ={"OPENAI_API_KEY": "sk-test"})
    manager.load()
    return manager


# ---- 配置 ----


def test_auto_resume_spec_and_default_off(tmp_path: Path) -> None:
    specs = {spec.key: spec for spec in config_specs()}
    spec = specs["orchestration.auto_resume"]
    assert (spec.cli_flag, spec.env_var, spec.map_to, spec.default) == (
        "--orchestration.auto-resume",
        "CORE_ORCHESTRATION_AUTO_RESUME",
        "orchestration.auto_resume",
        False,
    )
    assert _manager(tmp_path).orchestration_auto_resume() is False
    enabled = _manager(tmp_path, "orchestration:\n  auto_resume: true\n")
    assert enabled.orchestration_auto_resume() is True


def test_auto_resume_invalid_blocks_load(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="auto_resume"):
        _manager(tmp_path, "orchestration:\n  auto_resume: maybe\n")


# ---- 有界退避状态 ----


def _state(tmp_path: Path) -> AutoResumeState:
    return AutoResumeState(tmp_path / "auto-resume.json")


def test_state_exponential_backoff_and_exhaustion(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert state.due("t1", now=1000.0)

    state.record_attempt("t1", now=1000.0)
    assert not state.due("t1", now=1059.9)  # 第 1 次退避 60s
    assert state.due("t1", now=1060.0)

    state.record_attempt("t1", now=1060.0)
    assert not state.due("t1", now=1179.9)  # 第 2 次退避 120s
    assert state.due("t1", now=1180.0)

    state.record_attempt("t1", now=1180.0)
    assert state.attempts("t1") == AUTO_RESUME_MAX_ATTEMPTS
    assert not state.due("t1", now=10**9)  # 达上限：时间再久也不再自动尝试


def test_state_clear_and_retain(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.record_attempt("t1", now=1000.0)
    state.record_attempt("t2", now=1000.0)
    state.clear("t1")
    assert state.due("t1", now=1000.0)
    assert not state.due("t2", now=1000.0)

    state.retain({"t2"})
    assert state.attempts("t1") == 0
    assert state.attempts("t2") == 1


def test_state_corrupt_file_is_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "auto-resume.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.warns(UserWarning):
        state = AutoResumeState(path)
    assert state.due("t1", now=1000.0)


# ---- 检查点重建 ----


def _plan(goal: str = "目标") -> Plan:
    return Plan(
        subtasks=[
            Subtask(id="1", goal="一", acceptance=""),
            Subtask(id="2", goal="二", acceptance=""),
        ],
        goal=goal,
        order=["1", "2"],
        waves=[["1"], ["2"]],
    )


def _put(  # noqa: PLR0913 — 测试夹具参数组
    store: CheckpointStore,
    checkpoint_id: str,
    task_id: str,
    ts: float,
    state: dict[str, Any],
    *,
    session_id: str = "sess",
) -> None:
    store.put(
        Checkpoint(
            checkpoint_id=checkpoint_id,
            ts=ts,
            task_id=task_id,
            session_id=session_id,
            parent_id=None,
        ),
        Snapshot(snapshot_id=f"snap-{checkpoint_id}", checkpoint_id=checkpoint_id, state=state),
    )


def _resume_state(goal: str = "目标", *, done: bool = False) -> dict[str, Any]:
    return {
        "plan": plan_to_dict(_plan(goal)),
        "outcomes": [{"subtask_id": "1", "ok": True, "reply": "上游答复"}],
        "done": done,
    }


def test_task_resumes_warns_on_unreadable_snapshot(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.jsonl")
    _put(store, "corrupt", "t-corrupt", 1.0, _resume_state())
    store.corrupt("corrupt")

    with pytest.warns(UserWarning, match="t-corrupt"):
        assert _task_resumes(CheckpointManager(store)) == []


def test_task_resumes_rebuilds_latest_and_skips(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.jsonl")
    _put(store, "t1-old", "t1", 1.0, _resume_state("旧"))
    _put(store, "t1-new", "t1", 2.0, _resume_state("新"))
    _put(store, "done", "t-done", 3.0, _resume_state(done=True))
    _put(store, "turn", "turn.abc", 4.0, _resume_state())
    _put(store, "bad", "t-bad", 5.0, {"done": False})
    _put(store, "legacy", "t-legacy", 6.0, _resume_state("旧会话"), session_id="default")

    with pytest.warns(UserWarning, match="t-bad"):
        resumes = _task_resumes(CheckpointManager(store))

    by_id = {resume.task_id: resume for resume in resumes}
    assert set(by_id) == {"t1", "t-legacy"}
    assert by_id["t1"].goal == "新"  # 时间戳最新（落盘序无关）
    assert by_id["t1"].completed == frozenset({"1"})
    assert by_id["t1"].results == {"1": "上游答复"}
    assert by_id["t1"].session_id == "sess"
    assert by_id["t-legacy"].session_id == ""  # 旧占位值视作未归属


# ---- CLI 接线 ----


class _Orch:
    def __init__(self, *, fail_ids: set[str] | None = None) -> None:
        self.fail_ids = set(fail_ids or set())
        self.calls: list[dict[str, Any]] = []

    async def astream(  # noqa: PLR0913, PLR0917 — 对齐调度器签名
        self,
        task_id: str,
        goal: str,
        plan: Plan | None = None,
        completed: set[str] | None = None,
        results: dict[str, str] | None = None,
        session_id: str = "",
    ) -> AsyncIterator[LoopEvent]:
        self.calls.append(
            {
                "task_id": task_id,
                "goal": goal,
                "plan": plan,
                "completed": set(completed or set()),
                "results": dict(results or {}),
                "session_id": session_id,
            }
        )
        yield LoopEvent("task_started", {"task_id": task_id, "goal": goal})
        if task_id in self.fail_ids:
            yield LoopEvent(
                "task_failed", {"task_id": task_id, "code": "SUBTASK_VERIFY_FAILED", "reason": "x"}
            )
        else:
            yield LoopEvent("task_finished", {"outcomes": []})


def _resume(task_id: str = "t1") -> TaskResume:
    return TaskResume(
        task_id=task_id,
        goal="续跑目标",
        plan=_plan(),
        completed=frozenset({"1"}),
        results={"1": "上游答复"},
        session_id="sess",
    )


def _runtime(orch: _Orch, resumes: list[TaskResume], *, auto: bool) -> SimpleNamespace:
    return SimpleNamespace(
        orchestrator=orch,
        pending_resumes=lambda: list(resumes),
        config=SimpleNamespace(
            orchestration_auto_resume=lambda: auto,
            # 无人值守护栏（change 0280）：缺省关 ⇒ 既有路径逐字不变
            orchestration_task_timeout=lambda: 0,
            orchestration_failure_notify_file=lambda: "",
            orchestration_failure_notify_webhook=lambda: "",
        ),
        recover=lambda: [],
        recover_turns=lambda: [],
    )


def _registry_stub() -> type:
    class _Stub:
        def __init__(self, path: object = None) -> None:
            pass

        def create(self, mode: str) -> str:
            return "sess-new"

    return _Stub


def test_resume_all_runs_pending_and_skips_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    orch = _Orch()
    runtime = _runtime(orch, [_resume("t1"), _resume("t2")], auto=False)
    monkeypatch.setattr("core.entry.build_runtime", lambda config: runtime)

    rc = main(["task", "--resume-all"])
    assert rc == 0
    assert [call["task_id"] for call in orch.calls] == ["t1", "t2"]
    assert orch.calls[0]["completed"] == {"1"}
    assert orch.calls[0]["results"] == {"1": "上游答复"}
    assert not (tmp_path / "auto-resume.json").exists()  # 成功清零


def test_resume_all_no_pending_is_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    orch = _Orch()
    monkeypatch.setattr("core.entry.build_runtime", lambda config: _runtime(orch, [], auto=False))

    assert main(["task", "--resume-all"]) == 0
    assert orch.calls == []
    assert "无未完成任务" in capsys.readouterr().err


def test_auto_resume_runs_before_new_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    orch = _Orch()
    monkeypatch.setattr(
        "core.entry.build_runtime", lambda config: _runtime(orch, [_resume()], auto=True)
    )
    monkeypatch.setattr("core.entry.SessionRegistry", _registry_stub())

    rc = main(["task", "新目标", "--task-id", "new"])
    assert rc == 0
    assert [call["task_id"] for call in orch.calls] == ["t1", "new"]
    assert orch.calls[0]["plan"] is not None  # 续跑带重建计划
    assert orch.calls[1]["plan"] is None  # 新任务正常拆解


def test_auto_resume_off_does_not_run_pending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    orch = _Orch()
    monkeypatch.setattr(
        "core.entry.build_runtime", lambda config: _runtime(orch, [_resume()], auto=False)
    )
    monkeypatch.setattr("core.entry.SessionRegistry", _registry_stub())

    assert main(["task", "新目标", "--task-id", "new"]) == 0
    assert [call["task_id"] for call in orch.calls] == ["new"]


def test_auto_resume_respects_exhausted_but_resume_all_forces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    state = AutoResumeState(tmp_path / "auto-resume.json")
    for attempt in range(AUTO_RESUME_MAX_ATTEMPTS):
        state.record_attempt("t1", now=1000.0 + attempt)

    orch = _Orch()
    runtime = _runtime(orch, [_resume()], auto=True)
    monkeypatch.setattr("core.entry.build_runtime", lambda config: runtime)
    monkeypatch.setattr("core.entry.SessionRegistry", _registry_stub())

    assert main(["task", "新目标", "--task-id", "new"]) == 0
    assert [call["task_id"] for call in orch.calls] == ["new"]
    assert "跳过" in capsys.readouterr().err

    # 显式入口不受上限约束
    assert main(["task", "--resume-all"]) == 0
    assert [call["task_id"] for call in orch.calls] == ["new", "t1"]


def test_auto_resume_failure_keeps_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    orch = _Orch(fail_ids={"t1"})
    monkeypatch.setattr(
        "core.entry.build_runtime", lambda config: _runtime(orch, [_resume()], auto=True)
    )
    monkeypatch.setattr("core.entry.SessionRegistry", _registry_stub())

    assert main(["task", "新目标", "--task-id", "new"]) == 0  # 新任务本身成功
    state = AutoResumeState(tmp_path / "auto-resume.json")
    assert state.attempts("t1") == 1  # 失败保留：退避后下次重试
    assert "续跑失败" in capsys.readouterr().err
