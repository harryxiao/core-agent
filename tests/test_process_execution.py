"""0259 · code_run 进程治理：进程树终止、后台任务与进程管理工具。"""

from __future__ import annotations

import asyncio
import stat
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from core.plugin_registry import CoeffectResolver
from core.tools import (
    ToolErrorCode,
    ToolProvider,
    code_run,
    execution,
    process_kill,
    process_manage,
)
from core.tools.execution import ProcessRegistry

_LOG_MODE = 0o600
_TAIL_CHARS = 10


def _provider(*tools: Any) -> ToolProvider:
    resolver = CoeffectResolver()
    for coeffect in (
        "filesystem:read",
        "filesystem:write",
        "process:spawn",
        "process:read",
        "process:write",
    ):
        resolver.register(coeffect, True)
    provider = ToolProvider(coeffect_resolver=resolver)
    for tool in tools:
        provider.register(tool)
    return provider


def _marker_script(marker: Path, delay: float = 0.4) -> str:
    """启动孙进程（延迟写标记），再睡眠 5s —— 用于验证超时杀整棵树。"""
    grandchild = (
        "import time, pathlib; "
        f"time.sleep({delay}); pathlib.Path({str(marker)!r}).write_text('leak')"
    )
    return (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
        "time.sleep(5)\n"
    )


def _wait_exit(proc: Any, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            return True
        time.sleep(0.05)
    return False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 进程组探针")
def test_foreground_timeout_kills_process_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """超时后直接子进程与孙进程都被终止，孙进程不再产生副作用。"""
    marker = tmp_path / "grandchild-wrote"
    provider = _provider(code_run())
    result = provider.invoke(
        "tools.code_run",
        {"script": _marker_script(marker), "type": "python", "timeout": 0.3},
        trace_id="t",
        approved=True,
    )
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.TIMEOUT

    time.sleep(0.8)  # 若孙进程逃逸，它会在 0.4s 后写标记
    assert not marker.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 进程组探针")
def test_cancel_kills_process_tree(tmp_path: Path) -> None:
    """协程被取消（非超时）同样终止进程树。"""
    marker = tmp_path / "cancelled-grandchild"
    provider = _provider(code_run())

    async def main() -> None:
        task = asyncio.create_task(
            provider.ainvoke(
                "tools.code_run",
                {"script": _marker_script(marker), "type": "python", "timeout": 30},
                trace_id="t",
                approved=True,
            )
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    time.sleep(0.8)
    assert not marker.exists()


def test_foreground_decodes_invalid_utf8_with_replacement() -> None:
    """子进程原始字节以 UTF-8 解码，非法字节替换而非抛错。"""
    provider = _provider(code_run())
    result = provider.invoke(
        "tools.code_run",
        {"script": "import sys; sys.stdout.buffer.write(b'\\xff')", "type": "python"},
        trace_id="t",
        approved=True,
    )
    assert result.ok and result.data["returncode"] == 0
    assert "�" in result.data["stdout"]


@pytest.mark.parametrize("timeout", [0, -1, 601, float("nan"), float("inf")])
def test_timeout_out_of_range_rejected(monkeypatch: pytest.MonkeyPatch, timeout: float) -> None:
    """越界 / 非有限 timeout 结构化拒绝，不启动子进程。"""
    launched: list[Any] = []

    async def fake_exec(*_cmd: Any, **_kw: Any) -> Any:
        launched.append(_cmd)
        raise AssertionError("不应启动子进程")

    monkeypatch.setattr(execution, "_create_subprocess_exec", fake_exec)
    provider = _provider(code_run())
    result = provider.invoke(
        "tools.code_run",
        {"script": "print(1)", "type": "python", "timeout": timeout},
        trace_id="t",
        approved=True,
    )
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.EXECUTION_FAILED
    assert "timeout" in result.error.message.lower()
    assert launched == []


def test_foreground_uses_new_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """POSIX 前景以 start_new_session 启动（进程组隔离）。"""
    captured: dict[str, Any] = {}

    class _Proc:
        returncode = 0
        pid = 11

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"out", b""

    async def fake_exec(*_cmd: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return _Proc()

    monkeypatch.setattr(execution, "_IS_WINDOWS", False)
    monkeypatch.setattr(execution, "_create_subprocess_exec", fake_exec)
    result = asyncio.run(execution.run_foreground(["echo"], timeout=1.0))
    assert result.stdout == "out"
    assert captured["start_new_session"] is True
    assert "creationflags" not in captured


def test_windows_foreground_uses_creationflags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows 前景以新进程组启动，且不传 start_new_session。"""
    captured: dict[str, Any] = {}

    class _Proc:
        returncode = 0
        pid = 12

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def fake_exec(*_cmd: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return _Proc()

    monkeypatch.setattr(execution, "_IS_WINDOWS", True)
    monkeypatch.setattr(execution, "_create_subprocess_exec", fake_exec)
    asyncio.run(execution.run_foreground(["cmd"], timeout=1.0))
    assert captured["creationflags"] == execution._CREATE_NEW_PROCESS_GROUP
    assert "start_new_session" not in captured


def test_windows_kill_uses_taskkill_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows 进程树终止走 taskkill /T /F。"""
    calls: list[Any] = []

    class _Proc:
        pid = 4242

        def kill(self) -> None:  # pragma: no cover - 不应走到回退
            raise AssertionError("taskkill 成功时不应回退 proc.kill")  # noqa: TRY003

    def fake_run(cmd: Any, **_kw: Any) -> Any:
        calls.append(cmd)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(execution, "_IS_WINDOWS", True)
    monkeypatch.setattr(execution.subprocess, "run", fake_run)
    execution.kill_process_tree(_Proc())
    assert calls == [["taskkill", "/PID", "4242", "/T", "/F"]]


def test_background_returns_pid_and_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """后台任务立即返回 pid 与 0600 日志；tools.process 可查状态与输出。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    registry = ProcessRegistry()
    provider = _provider(
        code_run(registry=registry),
        process_manage(registry=registry),
        process_kill(registry=registry),
    )

    started = provider.invoke(
        "tools.code_run",
        {
            "script": "import time; print('bg-ok', flush=True); time.sleep(30)",
            "type": "python",
            "background": True,
        },
        trace_id="t",
        approved=True,
    )
    assert started.ok
    pid = started.data["pid"]
    output_path = Path(started.data["output_path"])
    assert started.data["background"] is True
    assert output_path.is_file()
    if sys.platform != "win32":
        assert stat.S_IMODE(output_path.stat().st_mode) & 0o777 == _LOG_MODE

    status = provider.invoke("tools.process", {"action": "status", "pid": pid}, trace_id="t")
    assert status.ok and status.data["found"] is True and status.data["running"] is True
    listed = provider.invoke("tools.process", {"action": "list"}, trace_id="t")
    assert listed.ok and [job["pid"] for job in listed.data["jobs"]] == [pid]

    output = ""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        out = provider.invoke("tools.process", {"action": "output", "pid": pid}, trace_id="t")
        if out.ok and "bg-ok" in out.data["output"]:
            output = out.data["output"]
            break
        time.sleep(0.05)
    assert "bg-ok" in output

    killed = provider.invoke("tools.process_kill", {"pid": pid}, trace_id="t", approved=True)
    assert killed.ok and killed.data["found"] is True and killed.data["killed"] is True
    assert _wait_exit(registry.get(pid).proc)  # type: ignore[union-attr]


def test_background_output_tail_is_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """tools.process output 只回尾部且有界。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    registry = ProcessRegistry()
    provider = _provider(code_run(registry=registry), process_manage(registry=registry))
    started = provider.invoke(
        "tools.code_run",
        {"script": "print('x' * 5000)", "type": "python", "background": True},
        trace_id="t",
        approved=True,
    )
    assert started.ok
    pid = started.data["pid"]
    registry.get(pid).proc.wait(timeout=10)  # type: ignore[union-attr]

    out = provider.invoke(
        "tools.process", {"action": "output", "pid": pid, "max_chars": _TAIL_CHARS}, trace_id="t"
    )
    assert out.ok and len(out.data["output"]) <= _TAIL_CHARS


def test_process_kill_requires_approval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """process_kill 不可逆 ⇒ 无批准时 fail-closed。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    registry = ProcessRegistry()
    provider = _provider(code_run(registry=registry), process_kill(registry=registry))
    started = provider.invoke(
        "tools.code_run",
        {"script": "import time; time.sleep(30)", "type": "python", "background": True},
        trace_id="t",
        approved=True,
    )
    assert started.ok
    pid = started.data["pid"]
    blocked = provider.invoke("tools.process_kill", {"pid": pid}, trace_id="t")
    assert blocked.ok is False
    assert blocked.error is not None and blocked.error.code == ToolErrorCode.IRREVERSIBLE_BLOCKED
    provider.invoke("tools.process_kill", {"pid": pid}, trace_id="t", approved=True)
    assert _wait_exit(registry.get(pid).proc)  # type: ignore[union-attr]


def test_unknown_pid_found_false() -> None:
    """注册表外 pid 不触达进程，返回 found=False。"""
    registry = ProcessRegistry()
    provider = _provider(process_manage(registry=registry), process_kill(registry=registry))
    status = provider.invoke("tools.process", {"action": "status", "pid": 999999}, trace_id="t")
    assert status.ok and status.data["found"] is False
    killed = provider.invoke("tools.process_kill", {"pid": 999999}, trace_id="t", approved=True)
    assert killed.ok and killed.data["found"] is False


def test_registry_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """注册表满且无已退出项 ⇒ 拒绝新后台任务，不杀活进程腾位。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    registry = ProcessRegistry(max_jobs=1)
    provider = _provider(code_run(registry=registry))
    first = provider.invoke(
        "tools.code_run",
        {"script": "import time; time.sleep(30)", "type": "python", "background": True},
        trace_id="t",
        approved=True,
    )
    assert first.ok
    second = provider.invoke(
        "tools.code_run",
        {"script": "import time; time.sleep(30)", "type": "python", "background": True},
        trace_id="t",
        approved=True,
    )
    assert second.ok is False
    assert second.error is not None and second.error.code == ToolErrorCode.EXECUTION_FAILED
    assert "上限" in second.error.message
    job = registry.get(first.data["pid"])
    assert job is not None and job.proc.poll() is None
    execution.kill_process_tree(job.proc)
    _wait_exit(job.proc)


def test_process_tool_declarations() -> None:
    """巡检只读可逆、终止不可逆写。"""
    registry = ProcessRegistry()
    inspect = process_manage(registry=registry).definition
    kill = process_kill(registry=registry).definition
    assert inspect.coeffects == ["process:read"] and inspect.reversible is True
    assert kill.coeffects == ["process:write"] and kill.reversible is False
