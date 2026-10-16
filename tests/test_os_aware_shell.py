"""0237 · 运行环境感知的 shell 方言（探测 / 提示块 / code_run / TUI）。"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

from core.loop.planner import LLMPlanner
from core.loop.protocol import LoopContext
from core.plugin_registry import CoeffectResolver
from core.tools import ToolErrorCode, ToolProvider, code_run
from core.tools.env_shell import (
    EnvironmentSnapshot,
    format_env_block,
    probe_environment,
    resolve_run_type,
    shell_argv,
)
from core.ui.repl import _tool_name, format_action_event


def _snap(**overrides: Any) -> EnvironmentSnapshot:
    base = dict(
        os="Windows",
        default_shell="powershell",
        shell_label="pwsh",
        path_style="windows",
        has_pwsh=True,
        has_powershell=True,
        has_bash=False,
    )
    base.update(overrides)
    return EnvironmentSnapshot(**base)  # type: ignore[arg-type]


def _provider(tool: Any = None) -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    resolver.register("process:spawn", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    provider.register(tool if tool is not None else code_run())
    return provider


# ---- 2.1 探测 ----


def test_probe_windows_defaults_powershell() -> None:
    snap = probe_environment(
        system=lambda: "Windows",
        which=lambda name: "C:\\x\\" + name if name in ("pwsh", "powershell") else None,
    )
    assert snap.os == "Windows"
    assert snap.default_shell == "powershell"
    assert snap.path_style == "windows"
    assert snap.has_pwsh is True


def test_probe_linux_defaults_bash() -> None:
    snap = probe_environment(
        system=lambda: "Linux",
        which=lambda name: "/bin/bash" if name == "bash" else None,
    )
    assert snap.os == "Linux"
    assert snap.default_shell == "bash"
    assert snap.has_bash is True


def test_probe_darwin_defaults_bash() -> None:
    snap = probe_environment(
        system=lambda: "Darwin",
        which=lambda name: "/bin/bash" if name == "bash" else None,
    )
    assert snap.default_shell == "bash"
    assert snap.os == "Darwin"


# ---- 2.2 planner ----


class _StubLLM:
    def completion(self, *_a: Any, **_k: Any) -> Any:
        raise AssertionError("不应调用")

    async def acompletion(self, *_a: Any, **_k: Any) -> Any:
        raise AssertionError("不应调用")


def _ctx() -> LoopContext:
    return LoopContext(messages=[{"role": "user", "content": "hi"}])


def test_planner_injects_env_block() -> None:
    planner = LLMPlanner(_StubLLM(), env_snapshot=_snap(os="Windows", default_shell="powershell"))
    prompt = planner._system_prompt(_ctx())  # noqa: SLF001
    assert "运行环境：" in prompt
    assert "Windows" in prompt
    assert "powershell" in prompt


def test_planner_omits_env_block_when_unset() -> None:
    planner = LLMPlanner(_StubLLM())
    prompt = planner._system_prompt(_ctx())  # noqa: SLF001
    assert "运行环境：" not in prompt


def test_format_env_block_mentions_path_and_syntax() -> None:
    body = format_env_block(_snap())
    assert "PowerShell" in body or "powershell" in body
    assert "file_*" in body


# ---- 2.3–2.6 code_run ----


def test_resolve_run_type_defaults() -> None:
    assert resolve_run_type(None, _snap()) == "powershell"
    assert resolve_run_type("", _snap(os="Linux", default_shell="bash")) == "bash"
    assert resolve_run_type("python", _snap()) == "python"


def test_shell_argv_powershell_prefers_pwsh() -> None:
    argv = shell_argv("powershell", "Get-ChildItem", _snap(has_pwsh=True))
    assert argv[:3] == ["pwsh", "-NoProfile", "-Command"]


def test_shell_argv_missing_powershell_raises() -> None:
    with pytest.raises(ValueError, match="PowerShell"):
        shell_argv(
            "powershell",
            "1",
            _snap(has_pwsh=False, has_powershell=False),
        )


def test_shell_argv_missing_bash_raises() -> None:
    with pytest.raises(ValueError, match="bash"):
        shell_argv("bash", "echo hi", _snap(has_bash=False))


def test_code_run_powershell_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **_kw: Any) -> Any:
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("core.tools.builtin.subprocess.run", fake_run)
    provider = _provider(code_run(env_snapshot=_snap(has_pwsh=True)))
    result = provider.invoke(
        "tools.code_run",
        {"script": "Write-Output 1", "type": "powershell"},
        trace_id="t",
        approved=True,
    )
    assert result.ok
    assert captured["cmd"][0] == "pwsh"
    assert "-Command" in captured["cmd"]
    assert result.data["type"] == "powershell"


def test_code_run_powershell_unavailable_structured() -> None:
    provider = _provider(code_run(env_snapshot=_snap(has_pwsh=False, has_powershell=False)))
    result = provider.invoke(
        "tools.code_run",
        {"script": "1", "type": "powershell"},
        trace_id="t",
        approved=True,
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ToolErrorCode.EXECUTION_FAILED
    assert "PowerShell" in result.error.message


def test_code_run_default_type_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **_kw: Any) -> Any:
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("core.tools.builtin.subprocess.run", fake_run)
    provider = _provider(code_run(env_snapshot=_snap()))
    result = provider.invoke("tools.code_run", {"script": "Get-Date"}, trace_id="t", approved=True)
    assert result.ok
    assert captured["cmd"][0] == "pwsh"
    assert result.data["type"] == "powershell"


def test_code_run_default_type_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **_kw: Any) -> Any:
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("core.tools.builtin.subprocess.run", fake_run)
    linux = _snap(
        os="Linux",
        default_shell="bash",
        shell_label="bash",
        path_style="posix",
        has_pwsh=False,
        has_powershell=False,
        has_bash=True,
    )
    provider = _provider(code_run(env_snapshot=linux))
    result = provider.invoke("tools.code_run", {"script": "echo hi"}, trace_id="t", approved=True)
    assert result.ok
    assert captured["cmd"][:2] == ["bash", "-c"]
    assert result.data["type"] == "bash"


def test_code_run_bash_unavailable_no_fallback() -> None:
    provider = _provider(code_run(env_snapshot=_snap(has_bash=False, has_pwsh=True)))
    result = provider.invoke(
        "tools.code_run",
        {"script": "echo hi", "type": "bash"},
        trace_id="t",
        approved=True,
    )
    assert result.ok is False
    assert result.error is not None and "bash" in result.error.message.lower()


def test_code_run_python_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **_kw: Any) -> Any:
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="42\n", stderr="")

    monkeypatch.setattr("core.tools.builtin.subprocess.run", fake_run)
    provider = _provider(code_run(env_snapshot=_snap()))
    result = provider.invoke(
        "tools.code_run",
        {"script": "print(42)", "type": "python"},
        trace_id="t",
        approved=True,
    )
    assert result.ok
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][1] == "-c"


# ---- 2.7 TUI ----


def test_tui_code_run_name_by_type() -> None:
    assert _tool_name("tools.code_run", {"type": "powershell", "script": "x"}) == "PowerShell"
    assert _tool_name("tools.code_run", {"type": "bash", "script": "x"}) == "Bash"
    assert _tool_name("tools.code_run", {"type": "python", "script": "x"}) == "Python"
    assert _tool_name("tools.code_run", {"script": "x"}) == "Bash"


def test_format_action_powershell_title() -> None:
    line = format_action_event(
        "action_started",
        {
            "tool_id": "tools.code_run",
            "args": {"type": "powershell", "script": "Get-ChildItem"},
        },
    )
    assert line is not None
    assert line.startswith("PowerShell(Get-ChildItem)")
