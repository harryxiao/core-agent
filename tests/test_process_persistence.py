"""0266 · 后台进程跨重启登记：持久化、恢复、身份核对与拒绝终止。"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core.plugin_registry import CoeffectResolver
from core.tools import ToolProvider, execution, process_kill, process_manage
from core.tools.execution import ProcessRegistry

_REGISTRY_NAME = "processes.json"
_FILE_MODE = 0o600
_SLEEP_30 = "import time; time.sleep(30)"


def _spawn() -> Any:
    return execution.spawn_background([sys.executable, "-c", _SLEEP_30], run_type="python")


def _cleanup(job: Any) -> None:
    if job.proc is not None:
        execution.kill_process_tree(job.proc)
        with contextlib.suppress(subprocess.TimeoutExpired, OSError):
            job.proc.wait(timeout=5)


def _write_registry(base: Path, entries: list[dict[str, Any]]) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    path = base / _REGISTRY_NAME
    path.write_text(json.dumps({"version": 1, "jobs": entries}), encoding="utf-8")
    return path


def _entry(pid: int, *, started_at: float = 1.0, ticks: int | None = None) -> dict[str, Any]:
    return {
        "pid": pid,
        "output_path": f"/tmp/{pid}.log",
        "started_at": started_at,
        "run_type": "python",
        "start_ticks": ticks,
    }


def _provider(*tools: Any) -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("process:read", True)
    resolver.register("process:write", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    for tool in tools:
        provider.register(tool)
    return provider


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=10)
    return int(proc.pid)


def test_add_persists_metadata_atomically(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """添加任务即落盘：0600、无临时文件残留、只有元数据字段。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    job = _spawn()
    try:
        registry = ProcessRegistry()
        registry.add(job)
        path = tmp_path / _REGISTRY_NAME
        assert path.is_file()
        if sys.platform != "win32":
            assert stat.S_IMODE(path.stat().st_mode) == _FILE_MODE
        assert sorted(item.name for item in tmp_path.iterdir()) == sorted(["run", _REGISTRY_NAME])
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert [item["pid"] for item in payload["jobs"]] == [job.pid]
        assert set(payload["jobs"][0]) == {
            "pid",
            "output_path",
            "started_at",
            "run_type",
            "start_ticks",
        }
    finally:
        _cleanup(job)


def test_registry_restores_running_job(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """新注册表恢复登记项：list / status / output 可用，运行中判定正确。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    job = _spawn()
    try:
        ProcessRegistry().add(job)
        restored = ProcessRegistry()
        loaded = restored.get(job.pid)
        assert loaded is not None and loaded.proc is None
        info = loaded.info()
        assert info["running"] is True
        assert info["restored"] is True
        assert info["returncode"] is None
        assert str(loaded.output_path) == str(job.output_path)

        provider = _provider(process_manage(registry=restored))
        status = provider.invoke(
            "tools.process", {"action": "status", "pid": job.pid}, trace_id="t"
        )
        assert status.ok and status.data["found"] is True
        assert status.data["restored"] is True and status.data["running"] is True
        listed = provider.invoke("tools.process", {"action": "list"}, trace_id="t")
        assert listed.ok and [item["pid"] for item in listed.data["jobs"]] == [job.pid]
        output = provider.invoke(
            "tools.process", {"action": "output", "pid": job.pid}, trace_id="t"
        )
        assert output.ok and output.data["found"] is True
    finally:
        _cleanup(job)


def test_restored_dead_entry_reports_not_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """已退出 pid 的恢复项保留可查，但 running=false。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    pid = _dead_pid()
    _write_registry(tmp_path, [_entry(pid)])
    registry = ProcessRegistry()
    restored = registry.get(pid)
    assert restored is not None
    info = restored.info()
    assert info["running"] is False
    assert info["restored"] is True


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="依赖 /proc starttime")
def test_restored_identity_mismatch_is_not_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """starttime 匹配才判运行中；不匹配（PID 复用）判已退出。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    ticks = execution._start_ticks(os.getpid())
    assert ticks is not None
    _write_registry(tmp_path, [_entry(os.getpid(), ticks=ticks)])
    assert ProcessRegistry().get(os.getpid()).info()["running"] is True  # type: ignore[union-attr]

    _write_registry(tmp_path, [_entry(os.getpid(), ticks=ticks + 1)])
    assert ProcessRegistry().get(os.getpid()).info()["running"] is False  # type: ignore[union-attr]


def test_restored_entry_kill_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """恢复项无进程句柄 ⇒ 批准后仍不终止，只返回 killed=false。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    job = _spawn()
    try:
        ProcessRegistry().add(job)
        restored = ProcessRegistry()
        provider = _provider(process_kill(registry=restored))
        result = provider.invoke(
            "tools.process_kill", {"pid": job.pid}, trace_id="t", approved=True
        )
        assert result.ok
        assert result.data["found"] is True
        assert result.data["killed"] is False
        assert result.data["restored"] is True
        assert job.proc.poll() is None
    finally:
        _cleanup(job)


def test_registry_load_tolerates_corruption_and_illegal_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """损坏 JSON 视为空；非法条目跳过，合法条目保留。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    (tmp_path / _REGISTRY_NAME).write_text("{not json", encoding="utf-8")
    assert ProcessRegistry().list() == []

    pid = _dead_pid()
    _write_registry(
        tmp_path,
        [
            {"pid": "not-an-int", "output_path": "/tmp/x", "started_at": 1, "run_type": "python"},
            {"pid": pid, "output_path": "/tmp/x", "started_at": float("nan"), "run_type": "python"},
            _entry(pid),
        ],
    )
    assert [job.pid for job in ProcessRegistry().list()] == [pid]


def test_registry_load_is_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """恢复条目数不超过 max_jobs，保留最新条目。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    pids = [_dead_pid() for _ in range(3)]
    _write_registry(tmp_path, [_entry(pid, started_at=float(i)) for i, pid in enumerate(pids)])
    assert [job.pid for job in ProcessRegistry(max_jobs=2).list()] == pids[1:]


def test_persistence_failure_does_not_block_spawn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """落盘失败被吞掉：任务仍登记可用。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")  # noqa: TRY003 — 模拟落盘失败

    monkeypatch.setattr(execution, "_save_registry", _boom)
    job = _spawn()
    try:
        registry = ProcessRegistry()
        registry.add(job)
        assert registry.get(job.pid) is job
    finally:
        _cleanup(job)


def test_replace_failure_keeps_previous_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """原子替换失败：旧文件逐字不变、临时文件清理，登记仍成功。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    pid = _dead_pid()
    path = _write_registry(tmp_path, [_entry(pid)])
    before = path.read_bytes()

    def _fail(_src: Any, _dst: Any) -> None:
        raise OSError("replace failed")  # noqa: TRY003 — 模拟替换失败

    monkeypatch.setattr(execution.os, "replace", _fail)
    job = _spawn()
    try:
        registry = ProcessRegistry()
        registry.add(job)
        assert registry.get(job.pid) is job
        assert path.read_bytes() == before
        assert sorted(item.name for item in tmp_path.iterdir()) == sorted(["run", _REGISTRY_NAME])
    finally:
        _cleanup(job)
