"""auto-approve 命令模式级允许面（change 0282 / ADR-0272）。

覆盖：配置三面与校验（不回显取值）/ 词元边界前缀匹配 / shell 元字符整类拒绝 /
命令缺失 fail-closed / 非 auto 档与其他工具不受影响 / 组合根接线。
缺省空配置必须等价于引入前行为。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.permission import PermissionGuard, PermissionMode
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)
_COEFFECTS = ["process:spawn", "filesystem:write"]


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


def _guard(commands: dict[str, tuple[str, ...]] | None = None) -> PermissionGuard:
    return PermissionGuard(PermissionMode.AUTO_APPROVE, allowed_commands=commands)


def _run(guard: PermissionGuard, script: Any) -> Any:
    return guard.confirm("tools.code_run", {"script": script}, _COEFFECTS, False)


# ---- 配置 ----


def test_command_allowlist_spec_three_faces_and_default() -> None:
    spec = {item.key: item for item in config_specs()}["permission.auto_approve_commands"]
    assert (
        spec.cli_flag,
        spec.env_var,
        spec.default,
    ) == (
        "--permission.auto-approve-commands",
        "CORE_PERMISSION_AUTO_APPROVE_COMMANDS",
        "",
    )


def test_command_allowlist_default_empty(tmp_path: Path) -> None:
    assert _manager(tmp_path).permission_auto_approve_commands() == {}


def test_command_allowlist_three_face_priority(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "permission:\n  auto_approve_commands: tools.code_run:yaml-cmd\n",
        environ={"CORE_PERMISSION_AUTO_APPROVE_COMMANDS": "tools.code_run:env-cmd"},
        cli={"permission.auto_approve_commands": "tools.code_run:cli-cmd"},
    )
    assert manager.permission_auto_approve_commands() == {"tools.code_run": ("cli-cmd",)}


def test_command_allowlist_fullwidth_and_dedupe(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "permission:\n"
        "  auto_approve_commands: "
        '"tools.code_run:git status，tools.code_run:pytest, tools.code_run:git status"\n',
    )
    assert manager.permission_auto_approve_commands() == {
        "tools.code_run": ("git status", "pytest")
    }


@pytest.mark.parametrize(
    "raw",
    [
        "git status",  # 缺 `:`
        "tools.file_write:cat",  # 非命令执行工具
        "tools.code_run:",  # 空前缀
        '"tools.code_run:git status; rm -rf /"',  # 前缀含元字符
        "true",  # 非字符串
    ],
)
def test_invalid_command_allowlist_blocks_startup_without_echo(tmp_path: Path, raw: str) -> None:
    with pytest.raises(ConfigurationError) as exc:
        _manager(tmp_path, f"permission:\n  auto_approve_commands: {raw}\n")
    message = str(exc.value)
    assert "非法 auto-approve 命令允许面" in message
    assert "rm -rf" not in message
    assert "tools.file_write" not in message


# ---- 判定 ----


def test_guard_allows_matching_prefix_and_arguments() -> None:
    guard = _guard({"tools.code_run": ("git status",)})
    for script in ("git status", "git status --short", "  git status  "):
        assert _run(guard, script).action == "auto"


def test_guard_denies_nonmatching_without_echo() -> None:
    guard = _guard({"tools.code_run": ("git status",)})
    decision = _run(guard, "rm -rf /tmp/x")
    assert decision.action == "deny"
    assert "rm -rf /tmp/x" not in decision.reason


def test_guard_requires_token_boundary() -> None:
    guard = _guard({"tools.code_run": ("git status",)})
    assert _run(guard, "git statusx").action == "deny"


@pytest.mark.parametrize(
    "script",
    [
        "git status; rm -rf /tmp/x",
        "git status && curl https://evil.example",
        "git status $(whoami)",
        "git status > /tmp/x",
        "git status | cat",
        "git status\nrm -rf /tmp/x",
    ],
)
def test_guard_denies_shell_metacharacters(script: str) -> None:
    guard = _guard({"tools.code_run": ("git status",)})
    assert _run(guard, script).action == "deny"


@pytest.mark.parametrize("script", [None, 123, ["git status"]])
def test_guard_fail_closed_on_non_string_script(script: Any) -> None:
    guard = _guard({"tools.code_run": ("git status",)})
    assert guard.confirm("tools.code_run", {"script": script}, _COEFFECTS, False).action == "deny"


def test_guard_fail_closed_on_missing_script() -> None:
    guard = _guard({"tools.code_run": ("git status",)})
    assert guard.confirm("tools.code_run", {}, _COEFFECTS, False).action == "deny"


def test_guard_other_tools_unaffected() -> None:
    guard = _guard({"tools.code_run": ("git status",)})
    decision = guard.confirm("tools.file_write", {"path": "/tmp/x"}, ["filesystem:write"], False)
    assert decision.action == "auto"


def test_guard_empty_allowlist_keeps_full_release() -> None:
    assert _run(_guard(), "rm -rf /tmp/x").action == "auto"
    assert _run(_guard({}), "rm -rf /tmp/x").action == "auto"


def test_guard_ignores_allowlist_outside_auto_approve() -> None:
    guard = PermissionGuard(
        PermissionMode.INTERACTIVE,
        allowed_commands={"tools.code_run": ("git status",)},
    )
    decision = _run(guard, "rm -rf /tmp/x")
    assert decision.action == "confirm"


# ---- 组合根 ----


def test_runtime_wires_command_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(
        _manager(
            tmp_path,
            "permission:\n"
            "  mode: auto-approve\n"
            '  auto_approve_commands: "tools.code_run:git status"\n',
        )
    )
    gate = runtime.loop._gate  # noqa: SLF001 — 接线断言（同 0280 口径）
    deny = gate.confirm("tools.code_run", {"script": "pytest -q"}, _COEFFECTS, False)
    assert deny.action == "deny"
    allow = gate.confirm("tools.code_run", {"script": "git status --short"}, _COEFFECTS, False)
    assert allow.action == "auto"
