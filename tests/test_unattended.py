"""无人值守 profile（change 0280 / ADR-0270）。

覆盖：四项配置三面与校验 / auto-approve 的 coeffect 允许面 / 整任务超时 /
整任务 token 预算（不重试不重拆）/ 失败通知 JSONL（脱敏、0600、取消不通知）。
缺省值（`"" / 0 / 0 / ""`）必须等价于引入前行为。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core import entry
from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.loop import Action, DefaultLoop, LoopEvent, LoopResult
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    OrchestrationError,
    OrchestrationErrorCode,
    Plan,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskResume,
    TaskScheduler,
    TaskState,
)
from core.permission import (
    AccessControlError,
    PermissionErrorCode,
    PermissionGuard,
    PermissionMode,
    PermissionModeGate,
)
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)
_CANARY = "sk-abcdefghijklmnop"
_FILE_MODE = 0o600


def _manager(
    tmp_path: Path,
    extra: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
) -> ConfigManager:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    manager = ConfigManager(
        yaml_path=cfg,
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    manager.load()
    return manager


# ---- 配置：单一真源与缺省 ----


def test_specs_declare_unattended_keys() -> None:
    specs = {spec.key: spec for spec in config_specs()}
    assert (
        specs["permission.auto_approve_coeffects"].cli_flag,
        specs["permission.auto_approve_coeffects"].env_var,
        specs["permission.auto_approve_coeffects"].default,
    ) == (
        "--permission.auto-approve-coeffects",
        "CORE_PERMISSION_AUTO_APPROVE_COEFFECTS",
        "",
    )
    assert (
        specs["orchestration.task_timeout"].cli_flag,
        specs["orchestration.task_timeout"].env_var,
        specs["orchestration.task_timeout"].default,
    ) == ("--orchestration.task-timeout", "CORE_ORCHESTRATION_TASK_TIMEOUT", 0)
    assert (
        specs["orchestration.task_token_budget"].cli_flag,
        specs["orchestration.task_token_budget"].env_var,
        specs["orchestration.task_token_budget"].default,
    ) == ("--orchestration.task-token-budget", "CORE_ORCHESTRATION_TASK_TOKEN_BUDGET", 0)
    assert (
        specs["orchestration.failure_notify_file"].cli_flag,
        specs["orchestration.failure_notify_file"].env_var,
        specs["orchestration.failure_notify_file"].default,
    ) == (
        "--orchestration.failure-notify-file",
        "CORE_ORCHESTRATION_FAILURE_NOTIFY_FILE",
        "",
    )


def test_defaults_are_all_off(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.permission_auto_approve_coeffects() == []
    assert manager.orchestration_task_timeout() == 0
    assert manager.orchestration_task_token_budget() == 0
    assert manager.orchestration_failure_notify_file() == ""


def test_values_from_yaml_and_allowlist_normalization(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "permission:\n"
        "  auto_approve_coeffects: filesystem:write, process:spawn,filesystem:write\n"
        "orchestration:\n"
        "  task_timeout: 30\n"
        "  task_token_budget: 5000\n"
        "  failure_notify_file: /tmp/core-notify.jsonl\n",
    )
    assert manager.permission_auto_approve_coeffects() == ["filesystem:write", "process:spawn"]
    assert manager.orchestration_task_timeout() == 30  # noqa: PLR2004 — 即 yaml 取值
    assert manager.orchestration_task_token_budget() == 5000  # noqa: PLR2004 — 即 yaml 取值
    assert manager.orchestration_failure_notify_file() == "/tmp/core-notify.jsonl"


def test_env_overrides_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "orchestration:\n  task_timeout: 30\n",
        environ={
            "CORE_ORCHESTRATION_TASK_TIMEOUT": "60",
            "CORE_PERMISSION_AUTO_APPROVE_COEFFECTS": "filesystem:read",
        },
    )
    assert manager.orchestration_task_timeout() == 60  # noqa: PLR2004 — 即 env 取值
    assert manager.permission_auto_approve_coeffects() == ["filesystem:read"]


@pytest.mark.parametrize("value", ["-1", "2.5", "abc", "true"])
def test_invalid_task_timeout_blocks_startup(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError, match="非法整任务超时"):
        _manager(tmp_path, f"orchestration:\n  task_timeout: {value}\n")


@pytest.mark.parametrize("value", ["-1", "2.5", "abc", "true"])
def test_invalid_token_budget_blocks_startup(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError, match="非法整任务 token 预算"):
        _manager(tmp_path, f"orchestration:\n  task_token_budget: {value}\n")


@pytest.mark.parametrize("value", ["filesystem", "filesystem:", ":write", "FS:write", "a:b:c"])
def test_invalid_coeffect_entry_blocks_startup(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError, match="非法 auto-approve 允许面"):
        _manager(tmp_path, f"permission:\n  auto_approve_coeffects: {value}\n")


def test_non_string_notify_path_blocks_startup(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="非法失败通知文件"):
        _manager(tmp_path, "orchestration:\n  failure_notify_file: true\n")


# ---- 允许面：auto-approve 全含判定 ----


def test_auto_approve_allowlist_permits_declared_subset() -> None:
    gate = PermissionModeGate(
        PermissionMode.AUTO_APPROVE, allowed_coeffects=frozenset({"filesystem:write"})
    )
    decision = gate.authorize("tools.file_write", "x", ["filesystem:write"])
    assert decision.allowed is True
    assert decision.approval_required is False


def test_auto_approve_allowlist_denies_outside() -> None:
    gate = PermissionModeGate(
        PermissionMode.AUTO_APPROVE, allowed_coeffects=frozenset({"filesystem:write"})
    )
    with pytest.raises(AccessControlError) as exc:
        gate.authorize("tools.web_fetch", "https://x", ["network:outbound"])
    assert exc.value.code is PermissionErrorCode.PERMISSION_DENIED


def test_auto_approve_allowlist_requires_all_declared_coeffects() -> None:
    gate = PermissionModeGate(
        PermissionMode.AUTO_APPROVE, allowed_coeffects=frozenset({"filesystem:write"})
    )
    with pytest.raises(AccessControlError, match="process:spawn"):
        gate.authorize("tools.code_run", "x", ["filesystem:write", "process:spawn"])


def test_empty_allowlist_keeps_full_release() -> None:
    for allowed in (None, frozenset()):
        gate = PermissionModeGate(PermissionMode.AUTO_APPROVE, allowed_coeffects=allowed)
        assert gate.authorize("tools.web_fetch", "x", ["network:outbound"]).allowed is True


def test_allowlist_ignored_outside_auto_approve() -> None:
    gate = PermissionModeGate(
        PermissionMode.INTERACTIVE, allowed_coeffects=frozenset({"filesystem:write"})
    )
    # high-risk 仍按 interactive 语义要求审批，允许面不改变结果
    assert gate.authorize("delete", "/prod", []).approval_required is True


def test_guard_denies_before_automatic_pass() -> None:
    guard = PermissionGuard(mode="auto-approve", allowed_coeffects=frozenset({"filesystem:write"}))
    decision = guard.confirm("tools.web_fetch", {"url": "https://x"}, ["network:outbound"], True)
    assert decision.action == "deny"
    allowed = guard.confirm("tools.file_write", {"path": "x"}, ["filesystem:write"], False)
    assert allowed.action == "auto"


def test_runtime_wires_allowlist_and_token_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(
        _manager(
            tmp_path,
            "permission:\n"
            "  mode: auto-approve\n"
            "  auto_approve_coeffects: filesystem:write\n"
            "orchestration:\n"
            "  task_token_budget: 99\n",
        )
    )
    assert runtime.orchestrator._task_token_budget == 99  # noqa: SLF001, PLR2004
    denied = runtime.loop._gate.confirm(  # noqa: SLF001 — 接线断言（同 0279 口径）
        "tools.web_fetch", {"url": "https://x"}, ["network:outbound"], True
    )
    assert denied.action == "deny"


# ---- token 记账与整任务预算 ----


class _TokenLoop(DefaultLoop):
    """每次执行报告固定 token 记账值并计数（预算用例）。"""

    def __init__(self, tokens: int) -> None:
        self.tokens = tokens
        self.calls = 0
        super().__init__(planner=lambda ctx: Action(args={"reply": "ok"}))

    async def astream(  # type: ignore[override] — 伪造终态载荷（token 预算用例）
        self, user_input: str, *, session_id: str = ""
    ) -> AsyncIterator[LoopEvent]:
        self.calls += 1
        yield LoopEvent(
            "loop_finished",
            LoopResult(reply="ok", trace_id="t", token_used=self.tokens),
        )


def _scheduler(loop: DefaultLoop, *, budget: int, planner_calls: list[int]) -> TaskScheduler:
    def planner(goal: str) -> list[Subtask]:
        planner_calls[0] += 1
        return [
            Subtask(id="a1", goal="one", acceptance=""),
            Subtask(id="a2", goal="two", acceptance=""),
        ]

    return TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(
            agents=[AgentProfile(agent_id="a", capabilities=["one", "two"], loop=loop)]
        ),
        state_machine=StateMachine(),
        task_token_budget=budget,
    )


def test_loop_result_token_used_default_and_filled() -> None:
    assert LoopResult(reply="x", trace_id="t").token_used == 0
    result = asyncio.run(DefaultLoop().arun("ping"))
    assert result.token_used > 0


def test_token_budget_exceeded_fails_without_retry_or_replan() -> None:
    loop = _TokenLoop(60)
    planner_calls = [0]
    scheduler = _scheduler(loop, budget=100, planner_calls=planner_calls)
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("t", "goal"))
    assert exc.value.code == OrchestrationErrorCode.TASK_TOKEN_BUDGET_EXCEEDED
    assert loop.calls == 2  # noqa: PLR2004 — 两个子任务各执行一次，无重试
    assert planner_calls[0] == 1  # 无重拆
    assert scheduler._state_machine.state("t") == TaskState.FAILED  # noqa: SLF001


def test_zero_budget_does_not_change_outcome() -> None:
    loop = _TokenLoop(10**9)
    planner_calls = [0]
    scheduler = _scheduler(loop, budget=0, planner_calls=planner_calls)
    outcomes = asyncio.run(scheduler.run("t", "goal"))
    assert all(o.ok for o in outcomes)
    assert scheduler._state_machine.state("t") == TaskState.DONE  # noqa: SLF001


def test_negative_token_budget_rejected() -> None:
    with pytest.raises(OrchestrationError):
        TaskScheduler(
            decomposer=SubtaskDecomposer(),
            router=MultiAgentRouter(agents=[]),
            state_machine=StateMachine(),
            task_token_budget=-1,
        )


# ---- 失败通知 ----


def test_notify_failure_appends_redacted_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "notify" / "failures.jsonl"
    entry._notify_failure(
        str(path),
        task_id="t1",
        session_id="s1",
        goal=f"处理 {_CANARY}",
        code="TASK_TIMEOUT",
        reason=f"超过时限 {_CANARY}",
    )
    entry._notify_failure(str(path), task_id="t2", session_id="", goal="g", code="X", reason="r")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # noqa: PLR2004 — 追加而非覆盖
    first = json.loads(lines[0])
    assert first["task_id"] == "t1"
    assert first["code"] == "TASK_TIMEOUT"
    assert _CANARY not in lines[0]
    assert "<redacted>" in lines[0]
    assert path.stat().st_mode & 0o777 == _FILE_MODE


def test_notify_failure_empty_path_is_noop(tmp_path: Path) -> None:
    entry._notify_failure("", task_id="t", session_id="", goal="g", code="X", reason="r")  # 不抛
    assert list(tmp_path.iterdir()) == []


class _FailingOrchestrator:
    def __init__(self, code: str, reason: str = "boom") -> None:
        self.code = code
        self.reason = reason

    async def astream(self, *args: Any, **kwargs: Any) -> Any:
        yield LoopEvent(
            "task_failed",
            {"task_id": "t", "code": self.code, "reason": self.reason},
        )


def test_stream_task_notifies_on_failure(tmp_path: Path) -> None:
    path = tmp_path / "notify.jsonl"
    failed = asyncio.run(
        entry._stream_task(
            _FailingOrchestrator(
                OrchestrationErrorCode.SUBTASK_EXECUTION_FAILED, f"failed {_CANARY}"
            ),
            "t",
            "goal",
            None,
            None,
            None,
            "",
            notify_file=str(path),
        )
    )
    assert failed is True
    line = path.read_text(encoding="utf-8").strip()
    assert "SUBTASK_EXECUTION_FAILED" in line
    assert _CANARY not in line


def test_stream_task_does_not_notify_cancellation(tmp_path: Path) -> None:
    path = tmp_path / "notify.jsonl"
    failed = asyncio.run(
        entry._stream_task(
            _FailingOrchestrator(OrchestrationErrorCode.TASK_CANCELLED),
            "t",
            "goal",
            None,
            None,
            None,
            "",
            notify_file=str(path),
        )
    )
    assert failed is True
    assert not path.exists()


# ---- 整任务时限（入口层） ----


class _HangingOrchestrator:
    async def astream(self, *args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(30)
        yield LoopEvent("task_finished", {"task_id": "t", "outcomes": []})


def test_run_task_stream_enforces_timeout(tmp_path: Path) -> None:
    path = tmp_path / "notify.jsonl"
    with pytest.raises(TimeoutError):
        asyncio.run(
            entry._run_task_stream(
                _HangingOrchestrator(),
                "t",
                "goal",
                None,
                None,
                None,
                "",
                timeout=0.01,
                notify_file=str(path),
            )
        )


def test_run_task_stream_zero_timeout_is_unlimited() -> None:
    failed = asyncio.run(
        entry._run_task_stream(
            _FailingOrchestrator(OrchestrationErrorCode.PROGRESS_NOT_MET),
            "t",
            "goal",
            None,
            None,
            None,
            "",
            timeout=0,
            notify_file="",
        )
    )
    assert failed is True


def test_task_timeout_returns_nonzero_and_notifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "notify.jsonl"

    class _Config:
        def orchestration_auto_resume(self) -> bool:
            return False

        def orchestration_task_timeout(self) -> int:
            return 1

        def orchestration_failure_notify_file(self) -> str:
            return str(path)

    runtime = SimpleNamespace(
        config=_Config(),
        orchestrator=object(),
        recover=lambda: [],
        recover_turns=lambda: [],
    )
    monkeypatch.setattr(entry, "_config_manager", lambda args: object())
    monkeypatch.setattr(entry, "build_runtime", lambda manager: runtime)

    async def _timed_out(*args: Any, **kwargs: Any) -> bool:
        raise TimeoutError

    monkeypatch.setattr(entry, "_run_task_stream", _timed_out)
    args = SimpleNamespace(goal="goal", resume_id=None, resume_all=False, task_id="t1")
    assert entry._task(args) == 1
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["code"] == "TASK_TIMEOUT"
    assert line["task_id"] == "t1"


def test_auto_resume_timeout_keeps_checkpoint_and_notifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "notify.jsonl"
    resume = TaskResume(
        task_id="task-1",
        goal="goal",
        plan=Plan(subtasks=[Subtask(id="a", goal="g", acceptance="")], goal="goal"),
    )

    class _Config:
        def orchestration_task_timeout(self) -> int:
            return 1

        def orchestration_failure_notify_file(self) -> str:
            return str(path)

    runtime = SimpleNamespace(
        pending_resumes=lambda: [resume],
        config=_Config(),
        orchestrator=object(),
    )

    async def _timed_out(*args: Any, **kwargs: Any) -> bool:
        raise TimeoutError

    monkeypatch.setattr(entry, "_run_task_stream", _timed_out)
    assert entry._run_auto_resume(runtime, force=True) is True
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["code"] == "TASK_TIMEOUT"
    assert line["task_id"] == "task-1"
    assert time.time() - float(line["ts"]) < 60  # noqa: PLR2004 — 时间戳可解析且为当前时刻
