"""entry 单元测试（对齐契约红线：命令面 / 三级帮助 / 未知命令错误码 / 版本输出）。"""

from __future__ import annotations

import pytest

from core.entry import _build_parser, main

# cli-contract-baseline.md §2 顶层命令面（19 子命令 + 无子命令进 REPL）。
_TOP_LEVEL_COMMANDS = {
    "serve",
    "app",
    "start",
    "stop",
    "restart",
    "probe",
    "status",
    "doctor",
    "sessions",
    "config",
    "mcp",
    "plugin",
    "skill",
    "session",
    "run",
    "release",
    "pet",
    "summon",
    "recall",
}

# baseline §2.11 全局 flag（F1-F14）+ pet.*（ConfigSpec 单一真源生成）。
_GLOBAL_FLAGS = {
    "--profile",
    "--cwd",
    "--config",
    "--feature",
    "--verbose",
    "--quiet",
    "--log-level",
    "--version",
    "--permission-mode",
    "--llm.provider",
    "--llm.model",
    "--llm.endpoint",
    "--llm.api-key",
    "--im.gateway",
    "--im.corp-id",
    "--im.secret",
    "--pet-enabled",
    "--pet-dir",
}


def test_top_level_command_surface() -> None:
    parser = _build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert set(choices) >= _TOP_LEVEL_COMMANDS


def test_global_flags_surface() -> None:
    parser = _build_parser()
    flags = {opt for action in parser._actions for opt in action.option_strings}
    assert flags >= _GLOBAL_FLAGS


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "core-agent" in capsys.readouterr().out


def test_help_three_levels(capsys: pytest.CaptureFixture[str]) -> None:
    for argv in (["-h"], ["config", "-h"], ["config", "get", "-h"]):
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 0
    capsys.readouterr()


def test_unknown_command_errors() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["nonexistent"])
    assert exc_info.value.code != 0


def test_session_create_returns_id(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["session", "create"]) == 0
    assert len(capsys.readouterr().out.strip()) == 32  # noqa: PLR2004 — uuid4 hex 固定 32 位


def test_config_get_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config", "get", "permission.mode"]) == 0
    assert capsys.readouterr().out.strip() == "interactive"


def test_pet_disabled_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pet", "gather"]) == 0
    assert "宠物模式未启用" in capsys.readouterr().err


# ---- 已接线命令面（config/probe/sessions/release/plugin/skill） ----


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


def test_config_validate_valid(monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert main(["--config", _write_config(tmp_path), "config", "validate"]) == 0
    assert "配置有效" in capsys.readouterr().out


def test_config_validate_invalid(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("llm:\n  provider: litellm\n", encoding="utf-8")
    assert main(["--config", str(cfg), "config", "validate"]) == 1
    assert "无效" in capsys.readouterr().err


def test_config_show_json_masks_secret(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert main(["--config", _write_config(tmp_path), "config", "show", "--format", "json"]) == 0
    out = capsys.readouterr().out
    assert "${OPENAI_API_KEY}" in out
    assert "sk-test" not in out


def test_config_set_llm_model(monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert main(["--config", _write_config(tmp_path), "config", "set", "llm.model", "gpt-4o"]) == 0
    assert "已设置 llm.model=gpt-4o" in capsys.readouterr().out


def test_config_set_unsupported_key(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert main(["--config", _write_config(tmp_path), "config", "set", "pet.enabled", "true"]) == 1
    assert "暂不支持" in capsys.readouterr().err


def test_probe_alive_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["probe"]) == 0
    assert '"alive": true' in capsys.readouterr().out


def test_sessions_empty(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sessions"]) == 0
    assert "无活跃会话" in capsys.readouterr().out


def test_release_publish(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["release", "publish", "bundle-v1"]) == 0
    assert "已发布版本 bundle-v1" in capsys.readouterr().out


def test_release_rollback_no_history(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["release", "rollback"]) == 1
    assert "发布失败" in capsys.readouterr().err


def test_plugin_install_skill_local_path(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = tmp_path / "skill.json"
    manifest.write_text(
        '{"skill_id": "skills.demo.hello", "description": "hi", "param_schema": {}}',
        encoding="utf-8",
    )
    assert main(["plugin", "install", str(manifest), "--kind", "skill"]) == 0
    assert "已安装 skill 资产" in capsys.readouterr().out


def test_skill_remove_missing(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skill", "remove", "skills.demo.hello"]) == 1
    assert "技能未注册" in capsys.readouterr().err
