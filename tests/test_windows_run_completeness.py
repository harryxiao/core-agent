"""0240 · Windows 运行环境提示与 code_run 输出完整性。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

from core.plugin_registry import CoeffectResolver
from core.tools import ToolProvider, code_run
from core.tools.env_shell import EnvironmentSnapshot, format_env_block
from core.ui.api import UIAPILayer
from core.ui.repl import _tool_name, format_action_event


def _snap(**overrides: Any) -> EnvironmentSnapshot:
    base = dict(
        os="Windows",
        default_shell="powershell",
        shell_label="PowerShell 7+ (pwsh)",
        path_style="windows",
        has_pwsh=True,
        has_powershell=False,
        has_bash=False,
    )
    base.update(overrides)
    return EnvironmentSnapshot(**base)  # type: ignore[arg-type]


def _provider(tool: Any = None) -> ToolProvider:
    resolver = CoeffectResolver()
    for coeffect in ("filesystem:read", "filesystem:write", "process:spawn"):
        resolver.register(coeffect, True)
    provider = ToolProvider(coeffect_resolver=resolver)
    provider.register(tool if tool is not None else code_run())
    return provider


class _FakeProc:
    """异步子进程替身（change 0259 执行 seam）。"""

    returncode = 0
    pid = 999999

    def __init__(self, stdout: bytes) -> None:
        self._stdout = stdout

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""

    async def wait(self) -> int:
        return 0

    def kill(self) -> None:
        pass


def _capture_run(monkeypatch: pytest.MonkeyPatch, *, stdout: str = "") -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_exec(*cmd: str, **kwargs: Any) -> _FakeProc:
        captured["cmd"] = list(cmd)
        captured["kwargs"] = kwargs
        return _FakeProc(stdout.encode("utf-8"))

    monkeypatch.setattr("core.tools.execution._create_subprocess_exec", fake_exec)
    return captured


# ---- 2.1 环境块 ----


def test_env_block_lists_available_shells_and_version_label() -> None:
    body = format_env_block(_snap(has_bash=True))
    assert "pwsh" in body
    assert "bash" in body
    assert "PowerShell 7+" in body


def test_env_block_missing_default_shell_advises_python() -> None:
    snap = _snap(
        has_pwsh=False,
        has_powershell=False,
        has_bash=True,
        shell_label="powershell（未检测到解释器）",
    )
    body = format_env_block(snap)
    assert "type=python" in body
    assert "不可用" in body


def test_env_block_declares_fresh_process_and_cwd() -> None:
    body = format_env_block(_snap())
    assert "全新进程" in body
    assert "cd" in body
    assert "cwd" in body
    assert "~" in body


def test_env_block_bounded_python_fallback_rule() -> None:
    body = format_env_block(_snap())
    assert "回退" in body
    assert "type=python" in body
    assert "pathlib" in body
    assert "tempfile" in body
    assert "/tmp" in body  # 明示禁止硬编码该路径


def test_env_block_unknown_os_does_not_claim_bash() -> None:
    snap = _snap(
        os="Other",
        default_shell="unknown",
        shell_label="unknown",
        path_style="posix",
        has_pwsh=False,
        has_powershell=False,
        has_bash=False,
    )
    body = format_env_block(snap)
    assert "默认 shell：unknown" in body
    assert "默认壳为 bash" not in body
    assert "显式" in body


# ---- 2.2 code_run 输出完整性 ----


def test_code_run_decodes_utf8_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    _capture_run(monkeypatch, stdout="中文")
    provider = _provider(code_run(env_snapshot=_snap()))
    result = provider.invoke("tools.code_run", {"script": "echo hi"}, trace_id="t", approved=True)
    assert result.ok
    assert result.data["stdout"] == "中文"


def test_code_run_python_sets_utf8_io_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_run(monkeypatch)
    provider = _provider(code_run(env_snapshot=_snap()))
    provider.invoke(
        "tools.code_run",
        {"script": "print('中文')", "type": "python"},
        trace_id="t",
        approved=True,
    )
    child_env = captured["kwargs"]["env"]
    assert child_env["PYTHONIOENCODING"] == "utf-8"
    assert child_env["PATH"] == os.environ["PATH"]


def test_code_run_powershell_sets_utf8_output_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_run(monkeypatch)
    provider = _provider(code_run(env_snapshot=_snap()))
    script = "Write-Output 你好"
    provider.invoke(
        "tools.code_run",
        {"script": script, "type": "powershell"},
        trace_id="t",
        approved=True,
    )
    command = captured["cmd"][-1]
    assert captured["cmd"][0] == "pwsh"
    assert "[Console]::OutputEncoding" in command
    assert "UTF8Encoding" in command
    assert script in command


def test_code_run_cwd_expands_home(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_run(monkeypatch)
    provider = _provider(code_run(env_snapshot=_snap()))
    provider.invoke(
        "tools.code_run",
        {"script": "echo hi", "cwd": "~/work"},
        trace_id="t",
        approved=True,
    )
    assert captured["kwargs"]["cwd"] == str(Path.home() / "work")


def test_code_run_python_uses_current_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_run(monkeypatch)
    provider = _provider(code_run(env_snapshot=_snap()))
    provider.invoke(
        "tools.code_run", {"script": "print(1)", "type": "python"}, trace_id="t", approved=True
    )
    assert captured["cmd"][:2] == [sys.executable, "-c"]


# ---- 2.3 TUI 有效 type ----


def test_tui_code_run_uses_effective_default_shell() -> None:
    assert _tool_name("tools.code_run", {"script": "x"}, default_shell="powershell") == "PowerShell"
    assert _tool_name("tools.code_run", {"script": "x"}, default_shell="bash") == "Bash"


def test_tui_code_run_without_facts_is_neutral() -> None:
    assert _tool_name("tools.code_run", {"script": "x"}) == "Shell"
    assert _tool_name("tools.code_run", {"script": "x"}, default_shell="unknown") == "Shell"


def test_format_action_event_uses_default_shell() -> None:
    line = format_action_event(
        "action_started",
        {"tool_id": "tools.code_run", "args": {"script": "Get-Date"}},
        default_shell="powershell",
    )
    assert line is not None
    assert line.startswith("PowerShell(Get-Date)")


def test_ui_api_exposes_default_shell() -> None:
    assert UIAPILayer(env_snapshot=_snap()).default_shell == "powershell"
    assert UIAPILayer().default_shell is None
