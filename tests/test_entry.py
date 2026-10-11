"""entry 单元测试（对齐契约红线：命令面 / 三级帮助 / 未知命令错误码 / 版本输出）。"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

from core.configuration.models import LLMConfig
from core.deployment import ServeStateStore
from core.durability import (
    CheckpointManager,
    CheckpointStore,
    DurabilityError,
    DurabilityErrorCode,
)
from core.entry import _build_installer, _build_parser, _state_path, main
from core.loop import LoopEvent
from core.memory import FileBackend, MemoryEntry, MemoryStore, TranscriptStore
from core.notes import NoteEntry, NoteStore
from core.orchestration import Plan, Subtask, plan_to_dict
from core.pet.core import (
    FAILED,
    WOKEN,
    PetManager,
    PetSession,
    PetTask,
    PetTaskKind,
    WakeOutcome,
)
from core.plugin_registry import PluginInstaller
from core.ui import SessionRegistry

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
    "evolve",
    "skill",
    "session",
    "memory",
    "run",
    "task",
    "release",
    "pet",
    "summon",
    "recall",
    "time-travel",
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


def test_config_get_default(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    """无 yaml 层时回落内置缺省（显式指向不存在的配置，不依赖开发机本地 config.yaml）。"""
    argv = ["--config", str(tmp_path / "missing.yaml"), "config", "get", "permission.mode"]
    assert main(argv) == 0
    assert capsys.readouterr().out.strip() == "interactive"


def test_config_get_reads_yaml_layer(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    """账本 E22：`config get` 须与配置链同口径 —— config.yaml 里的值应被读到。

    回归：`entry._config` 此前用 `resolve(key, cli=, env=)`（漏 yaml 层）⇒ 配置文件里写了
    非缺省值仍显示缺省（E21 修 pet 门控时同型缺陷转出为本项）。
    """
    assert main(["--config", _write_config(tmp_path), "config", "get", "llm.model"]) == 0
    assert capsys.readouterr().out.strip() == "test-model"


def test_config_get_cli_overrides_yaml(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    """优先级链 CLI > yaml：`--llm.model` 压过 config.yaml。"""
    argv = [
        "--config",
        _write_config(tmp_path),
        "--llm.model",
        "cli-model",
        "config",
        "get",
        "llm.model",
    ]
    assert main(argv) == 0
    assert capsys.readouterr().out.strip() == "cli-model"


def test_pet_disabled_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pet", "gather"]) == 0
    assert "宠物模式未启用" in capsys.readouterr().err


def test_pet_yaml_admits_and_honors_persons_dir(tmp_path, monkeypatch, capsys) -> None:
    """pet 门控与 persona 目录走 ConfigSpec 三层链：yaml 里的 enabled/persons_dir 生效。

    回归账本 E21：CLI 前置判定此前只解析 CLI/env（漏 yaml 层），故 config.yaml 写了
    ``pet.enabled: true`` 也被判为未启用、``persons_dir`` 被静默忽略（回落 "./persons"）。
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    persons = tmp_path / "kennels"
    persons.mkdir()
    (persons / "xiaoju.md").write_text("name: 小橘\nspecies: 猫\n", encoding="utf-8")
    cfg = _write_pet_config(tmp_path, enabled=True, persons_dir=str(persons))

    assert main(["--config", cfg, "pet", "list"]) == 0
    captured = capsys.readouterr()
    assert "宠物模式未启用" not in captured.err  # yaml 的 enabled=true 被采信
    assert "xiaoju" in captured.out  # persons_dir 取自 yaml（非 cwd 下的 ./persons）


def test_pet_env_overrides_yaml(tmp_path, monkeypatch, capsys) -> None:
    """优先级链 CLI flag > env > yaml：env 显式关（false）压过 yaml 的 true。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_PET_ENABLED", "false")
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "list"]) == 0
    assert "宠物模式未启用" in capsys.readouterr().err


def test_pet_missing_config_file_is_tolerated(tmp_path, monkeypatch, capsys) -> None:
    """配置文件不存在：前置判定按「无 yaml 层」处理（不装配、不报错、退出 0）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    missing = tmp_path / "nope.yaml"

    assert main(["--config", str(missing), "pet", "list"]) == 0
    captured = capsys.readouterr()
    assert "宠物模式未启用" in captured.err
    assert "装配失败" not in captured.err  # 前置判定不因缺文件抛错


def test_pet_run_drives_restored_sessions(tmp_path, monkeypatch, capsys) -> None:
    """E28：`pet run` 从跨进程注册表恢复会话并交给驱动（间隔透传 + 一轮呈现 + 退出 0）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CORE_STATE_DIR", str(state))
    seeded = PetSession(session_id="p1")
    seeded.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="观察环境"))
    PetManager(state / "pets.json").register(seeded)

    seen: dict[str, object] = {}

    class _FakeDriver:
        """替身：记下构造实参与 run 的间隔，跑一轮即返回（不真沉睡）。"""

        def __init__(self, sessions) -> None:
            seen["sessions"] = list(sessions())

        def run(self, interval, *, on_tick=None) -> None:
            seen["interval"] = interval
            if on_tick is not None:
                on_tick([WakeOutcome("p1", WOKEN)])
                on_tick([WakeOutcome("p1", FAILED, "RuntimeError: loop 炸了")])

    monkeypatch.setattr("core.entry.PetWakeDriver", _FakeDriver)
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "run", "--interval", "0.25"]) == 0
    assert seen["interval"] == pytest.approx(0.25)
    assert [s.session_id for s in seen["sessions"]] == ["p1"]  # 注册表跨进程恢复
    captured = capsys.readouterr()
    assert "已开始驱动 1 只宠物会话" in captured.out
    assert "已驱动 1 只宠物" in captured.out
    assert "p1 唤醒失败" in captured.err


def test_pet_run_rejects_bad_interval(tmp_path, monkeypatch, capsys) -> None:
    """非法 / 非正间隔 ⇒ 用法错误 + 退出 1（不进常驻循环）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "run", "--interval", "0"]) == 1
    assert main(["--config", cfg, "pet", "run", "--interval", "abc"]) == 1
    assert "用法: core-agent pet run" in capsys.readouterr().err


def test_pet_run_without_pets_hints_and_exits_zero(tmp_path, monkeypatch, capsys) -> None:
    """无已注册会话：提示三入口激活并退出 0 —— 驱动不自动造宠物（激活归三入口）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "empty-state"))
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "run"]) == 0
    assert "当前无激活宠物" in capsys.readouterr().err


def _seed_pet(state, session_id: str = "p1") -> None:
    """向跨进程注册表种入一只运行中的宠物（控制面 CLI 用例用）。"""
    seeded = PetSession(session_id=session_id)
    seeded.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="观察环境"))
    PetManager(state / "pets.json").register(seeded)


def test_pet_status_cli_shows_structured_state(tmp_path, monkeypatch, capsys) -> None:
    """控制面 CLI：`pet status` 显示结构化状态（change 0088 / 用户诉求①）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CORE_STATE_DIR", str(state))
    _seed_pet(state)
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "status"]) == 0
    out = capsys.readouterr().out
    assert "p1" in out and "active" in out


def test_pet_sleep_and_wake_cli_roundtrip(tmp_path, monkeypatch, capsys) -> None:
    """控制面 CLI：`pet sleep` 让宠物入睡、`pet wake` 叫醒。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CORE_STATE_DIR", str(state))
    _seed_pet(state)
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "sleep", "p1"]) == 0
    assert "入睡" in capsys.readouterr().out
    assert main(["--config", cfg, "pet", "wake", "p1"]) == 0
    assert "叫醒" in capsys.readouterr().out


def test_pet_assign_cli_switches_job(tmp_path, monkeypatch, capsys) -> None:
    """控制面 CLI：`pet assign` 给（单）宠物换一件活（默认寻址）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CORE_STATE_DIR", str(state))
    _seed_pet(state)
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "assign", "整理收藏夹"]) == 0
    assert "派发" in capsys.readouterr().out


def test_pet_control_unknown_session_exits_1(tmp_path, monkeypatch, capsys) -> None:
    """未知会话 ⇒ 结构化拒绝 + 退出码 1（不静默成功）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CORE_STATE_DIR", str(state))
    _seed_pet(state)
    cfg = _write_pet_config(tmp_path, enabled=True)

    assert main(["--config", cfg, "pet", "sleep", "nope"]) == 1
    assert "PET_NOT_FOUND" in capsys.readouterr().err


def test_repl_wires_llm_config(monkeypatch, tmp_path) -> None:
    """无子命令进 REPL：真 runtime 装配 + 注入 LLM 配置（对齐 run 的同构入口）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, api=None, connect_impl=None, session_id="") -> None:
            captured["api"] = api

        def connect(self) -> None:
            return None

    monkeypatch.setattr("core.entry.CLIBridge", _FakeBridge)
    assert main(["--config", _write_config(tmp_path)]) == 0
    api = captured["api"]
    assert api.get_llm_config().model == "test-model"


def test_serve_wires_llm_config(monkeypatch, tmp_path) -> None:
    """serve 命令：真 runtime 装配 + 注入 LLM 配置到 WebBridge。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, api=None, serve_impl=None) -> None:
            captured["api"] = api

        def serve(self, host: str, port: int) -> None:
            return None

    monkeypatch.setattr("core.entry.WebBridge", _FakeBridge)
    assert main(["--config", _write_config(tmp_path), "serve"]) == 0
    api = captured["api"]
    assert api.get_llm_config().model == "test-model"


def test_app_wires_llm_config(monkeypatch, tmp_path) -> None:
    """app 命令：真 runtime 装配 + 注入 LLM 配置到 DesktopBridge。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, api=None, start_impl=None, port=None) -> None:
            captured["api"] = api
            captured["port"] = port

        def start_sidecar(self) -> None:
            return None

    monkeypatch.setattr("core.entry.DesktopBridge", _FakeBridge)
    assert main(["--config", _write_config(tmp_path), "app"]) == 0
    api = captured["api"]
    assert api.get_llm_config().model == "test-model"


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


def _write_pet_config(tmp_path, *, enabled: bool, persons_dir: str | None = None) -> str:
    cfg = tmp_path / "config.yaml"
    directory = persons_dir if persons_dir is not None else str(tmp_path / "persons")
    cfg.write_text(
        "llm:\n"
        "  provider: openai\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "pet:\n"
        f"  enabled: {'true' if enabled else 'false'}\n"
        f"  persons_dir: {directory}\n",
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


def test_config_validate_warns_on_unknown_section(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E18：未知段仅告警 —— 退出码仍为 0（不阻断），告警在 stderr 可见。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    path = _write_config(tmp_path)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "llmm:\n  model: typo\n", encoding="utf-8")
    with pytest.warns(UserWarning, match="未知配置段: llmm"):
        code = main(["--config", path, "config", "validate"])
    assert code == 0
    assert "配置有效" in capsys.readouterr().out


def test_config_validate_warns_on_unknown_feature_module(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E20①：features 段未知模块名仅告警 —— 退出码仍为 0（不阻断）。

    走**组合根注入**的已知模块名（`entry._config_manager`）⇒ 证明入口注入已接线，不只是单元。
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    path = _write_config(tmp_path)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "features:\n  peet: false\n", encoding="utf-8")
    with pytest.warns(UserWarning, match="未知功能开关: features.peet"):
        code = main(["--config", path, "config", "validate"])
    assert code == 0
    assert "配置有效" in capsys.readouterr().out


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


def test_probe_down_when_no_serve(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["probe"]) == 1
    assert '"alive": false' in capsys.readouterr().out


def test_probe_alive_when_serve_running(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    ServeStateStore(tmp_path / "state" / "serve.json").mark_running()  # 当前进程 pid，真实存活
    assert main(["probe"]) == 0
    assert '"alive": true' in capsys.readouterr().out


def test_sessions_empty(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sessions"]) == 0
    assert "无活跃会话" in capsys.readouterr().out


def _write_bundle_manifest(tmp_path, name: str, refs: list[tuple[str, int]]) -> pathlib.Path:
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "name": name,
                "plugin_refs": [{"plugin_id": pid, "generation": gen} for pid, gen in refs],
            }
        ),
        encoding="utf-8",
    )
    return path


def _release_hashes() -> dict[str, str]:
    data = json.loads(_state_path("releases.json").read_text(encoding="utf-8"))
    return {version: info["hash"] for version, info in data["releases"].items()}


def test_release_publish(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    """`release publish <制品清单>` ⇒ 经 composition 真口径哈希发布（change 0143 / E84-a）。"""
    manifest = _write_bundle_manifest(tmp_path, "bundle-v1", [("tools.code_run", 1)])
    assert main(["release", "publish", str(manifest)]) == 0
    assert "已发布版本 bundle-v1" in capsys.readouterr().out


def test_release_publish_hash_is_content_addressed(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """同内容异元信息（清单名 + bundle 名不同）⇒ 两条发布记录哈希**相同**；异内容 ⇒ 不同。"""
    same_a = _write_bundle_manifest(
        tmp_path, "release-a", [("tools.code_run", 1), ("tools.web_fetch", 2)]
    )
    same_b = _write_bundle_manifest(
        tmp_path, "release-b", [("tools.code_run", 1), ("tools.web_fetch", 2)]
    )
    other = _write_bundle_manifest(
        tmp_path, "release-c", [("tools.code_run", 2), ("tools.web_fetch", 2)]
    )
    for manifest in (same_a, same_b, other):
        assert main(["release", "publish", str(manifest)]) == 0
    capsys.readouterr()
    hashes = _release_hashes()
    assert hashes["release-a"] == hashes["release-b"], "内容相同 ⇒ 哈希相同（不取版本名）"
    assert hashes["release-c"] != hashes["release-a"], "内容不同 ⇒ 哈希不同"


def test_release_publish_missing_manifest_rejected(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """清单缺失 ⇒ 退出码 1 + 结构化报错，**不产假账**（SHALL NOT 退化为版本名哈希）。"""
    assert main(["release", "publish", str(tmp_path / "absent.json")]) == 1
    assert "发布失败" in capsys.readouterr().err
    assert not _state_path("releases.json").exists(), "拒绝发布即不落任何发布记录"


def test_release_publish_invalid_manifest_keeps_history(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """非法清单 ⇒ 拒绝且**既有发布记录不变**（先成功一条，再拿坏清单撞）。"""
    good = _write_bundle_manifest(tmp_path, "good", [("tools.code_run", 1)])
    broken = tmp_path / "broken.json"
    broken.write_text(
        json.dumps({"plugin_refs": [{"plugin_id": "tools.code_run"}]}), encoding="utf-8"
    )
    assert main(["release", "publish", str(good)]) == 0
    before = _release_hashes()
    capsys.readouterr()
    assert main(["release", "publish", str(broken)]) == 1
    assert "发布失败" in capsys.readouterr().err
    assert _release_hashes() == before


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


def test_plugin_install_records_ledger_and_uninstall(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """install 落账本（register）→ list 可见 → uninstall 清理（对齐 install_tools 全生命周期）。"""
    installer = _build_installer()
    monkeypatch.setattr("core.entry._build_installer", lambda: installer)
    manifest = tmp_path / "skill.json"
    manifest.write_text(
        '{"skill_id": "skills.demo.hello", "description": "hi", "param_schema": {}}',
        encoding="utf-8",
    )
    assert main(["plugin", "install", str(manifest), "--kind", "skill"]) == 0
    assert installer.installed() == [
        {"plugin_id": "skills.demo.hello", "kind": "skill", "source": "local-path"}
    ]
    assert main(["plugin", "list"]) == 0
    assert "skills.demo.hello" in capsys.readouterr().out
    assert main(["plugin", "uninstall", "skills.demo.hello"]) == 0
    assert installer.installed() == []


def test_plugin_install_runs_full_lifecycle(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI `plugin install` 须走完整生命周期（verify → install → register → activate）。

    change 0108 / 账本 E35：与 `tools.install` 同链（`installable` 声明 + plugin-registry spec
    「插件来源与安装」），此前 CLI 路径跳过 verify / activate。
    """
    calls: list[str] = []

    class _Recording(PluginInstaller):
        def verify(self, asset, signature) -> None:  # type: ignore[override]
            calls.append("verify")
            super().verify(asset, signature)

        def activate(self, plugin_id: str) -> None:
            calls.append("activate")
            super().activate(plugin_id)

    installer = _Recording(
        source_resolver=lambda source, location: {"skill_id": "skills.demo.hello"}
    )
    monkeypatch.setattr("core.entry._build_installer", lambda: installer)
    manifest = tmp_path / "skill.json"
    manifest.write_text('{"skill_id": "skills.demo.hello"}', encoding="utf-8")

    assert main(["plugin", "install", str(manifest), "--kind", "skill"]) == 0
    assert calls == ["verify", "activate"]


# ---- CLI 跨进程（真实子进程）----

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def _cli(*argv: str) -> subprocess.CompletedProcess[str]:
    """真实子进程跑 `python -m core.entry`（CORE_STATE_DIR 由 conftest 隔离，子进程继承）。"""
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    return subprocess.run(
        [sys.executable, "-m", "core.entry", *argv], capture_output=True, text=True, env=env
    )


def test_plugin_install_persists_across_processes(tmp_path) -> None:
    """CLI 是一次性进程：账本须落盘 —— 新进程 `plugin list` 仍见、`plugin uninstall` 可用。

    change 0109 / 账本 E36：此前 `_assets` 是进程内字典 ⇒ `plugin list` 恒「（无已安装资产）」、
    `plugin uninstall` 恒 `UNINSTALL_NOT_FOUND`（cli 类更是**一个字节都不落盘**）。
    """
    manifest = tmp_path / "cli.json"
    manifest.write_text(json.dumps({"name": "demo", "command": "echo"}), encoding="utf-8")

    installed = _cli("plugin", "install", str(manifest), "--kind", "cli")
    assert installed.returncode == 0, installed.stderr
    assert "已安装 cli 资产" in installed.stdout

    listed = _cli("plugin", "list")
    assert "demo (cli, local-path)" in listed.stdout

    removed = _cli("plugin", "uninstall", "demo")
    assert removed.returncode == 0, removed.stderr
    assert "（无已安装资产）" in _cli("plugin", "list").stdout


def test_skill_remove_missing(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skill", "remove", "skills.demo.hello"]) == 1
    assert "技能未注册" in capsys.readouterr().err


# ---- task：多任务编排入口 ----


class _StreamOrchestrator:
    """编排器桩：记录调用参数，依序回放进度事件。"""

    def __init__(self, events: list[tuple[str, dict[str, object]]]) -> None:
        self.events = events
        self.calls: dict[str, object] = {}

    async def astream(self, task_id: str, goal: str, **kwargs: object) -> object:
        self.calls = {"task_id": task_id, "goal": goal, **kwargs}
        for kind, payload in self.events:
            yield LoopEvent(kind, payload)


def _patch_runtime(  # noqa: PLR0913 — 测试桩装配参数组（checkpoints/time_travel/registry/handles）
    monkeypatch: pytest.MonkeyPatch,
    orch: _StreamOrchestrator,
    checkpoints: object,
    *,
    time_travel: object = None,
    registry: type | None = None,
    handles: list[object] | None = None,
) -> None:
    runtime = SimpleNamespace(
        orchestrator=orch,
        checkpoints=checkpoints,
        time_travel=time_travel,
        recover=lambda: handles or [],  # 启动扫描：未完成任务句柄（change 0191）
    )
    monkeypatch.setattr("core.entry.build_runtime", lambda config: runtime)
    if registry is not None:
        monkeypatch.setattr("core.entry.SessionRegistry", registry)


def _registry_stub(modes: list[str]) -> type:
    """会话注册表桩类：create 记录 mode 到闭包列表，返回固定会话标识。"""

    class _Stub:
        def __init__(self, path: object = None) -> None:
            pass

        def create(self, mode: str) -> str:
            modes.append(mode)
            return "sess-stub"

    return _Stub


def test_task_streams_progress_events(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    orch = _StreamOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "复合目标"}),
            ("plan_ready", {"subtasks": [{"id": "1"}], "waves": [["1"]]}),
            ("subtask_started", {"subtask_id": "1", "goal": "子目标"}),
            ("subtask_completed", {"subtask_id": "1", "ok": True}),
            ("task_finished", {"outcomes": [SimpleNamespace(ok=True)]}),
        ]
    )
    _patch_runtime(monkeypatch, orch, checkpoints=None, registry=_registry_stub([]))

    rc = main(["task", "复合目标", "--task-id", "t1"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "[task] 任务 t1：复合目标" in out
    assert "[plan] 拆解 1 个子任务" in out
    assert "[task_finished] 任务完成（1/1 子任务通过）" in out


def test_task_failed_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    orch = _StreamOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "g"}),
            (
                "task_failed",
                {
                    "task_id": "t1",
                    "code": "SUBTASK_VERIFY_FAILED",
                    "reason": "子任务校验失败: ['1']",
                },
            ),
        ]
    )
    _patch_runtime(monkeypatch, orch, checkpoints=None, registry=_registry_stub([]))

    rc = main(["task", "g", "--task-id", "t1"])

    assert rc == 1
    assert "[task_failed]" in capsys.readouterr().out


def test_task_requires_goal(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["task"]) == 1
    assert "用法" in capsys.readouterr().err


def test_task_resume_rebuilds_plan_and_completed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = Plan(
        subtasks=[
            Subtask(id="1", goal="已完成", acceptance=""),
            Subtask(id="2", goal="续跑部分", acceptance=""),
        ],
        goal="续跑目标",
        order=["1", "2"],
        waves=[["1"], ["2"]],
    )
    orch = _StreamOrchestrator([("task_started", {}), ("task_finished", {"outcomes": []})])
    cps = [SimpleNamespace(checkpoint_id="cp1", task_id="t1", session_id="default", ts=1.0)]
    snapshots = {
        "cp1": SimpleNamespace(
            state={
                "plan": plan_to_dict(plan),
                "outcomes": [{"subtask_id": "1", "ok": True, "reply": "上游答复"}],
                "done": False,
            }
        )
    }
    checkpoints = SimpleNamespace(
        list_checkpoints=lambda *, task_id=None: cps,
        get_snapshot=lambda checkpoint_id: snapshots[checkpoint_id],
    )
    _patch_runtime(monkeypatch, orch, checkpoints=checkpoints)

    rc = main(["task", "--resume", "t1"])

    assert rc == 0
    assert orch.calls["task_id"] == "t1"
    assert orch.calls["goal"] == "续跑目标"  # 目标自检查点计划重建
    assert isinstance(orch.calls["plan"], Plan)
    assert orch.calls["completed"] == {"1"}  # 已完成集回填，续跑跳过
    assert orch.calls["results"] == {"1": "上游答复"}  # 依赖交接上下文重建
    assert orch.calls["session_id"] == ""  # 旧占位值检查点 ⇒ 视作未归属（与既往一致）


# ---- task 会话归因（change 0190 / 账本 E127）----


def test_task_fresh_mints_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    orch = _StreamOrchestrator([("task_started", {}), ("task_finished", {"outcomes": []})])
    modes: list[str] = []
    _patch_runtime(monkeypatch, orch, checkpoints=None, registry=_registry_stub(modes))

    rc = main(["task", "g"])

    assert rc == 0
    assert modes == ["cli"]  # 经共享注册表铸会话（mode cli，session list 可见）
    assert orch.calls["session_id"] == "sess-stub"  # 会话标识透传至编排器


def test_task_resume_reuses_checkpoint_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = Plan(
        subtasks=[Subtask(id="1", goal="g", acceptance="")], goal="g", order=["1"], waves=[["1"]]
    )
    orch = _StreamOrchestrator([("task_started", {}), ("task_finished", {"outcomes": []})])
    cps = [SimpleNamespace(checkpoint_id="cp1", task_id="t1", session_id="orig-sess", ts=1.0)]
    snapshots = {"cp1": SimpleNamespace(state={"plan": plan_to_dict(plan), "done": False})}
    checkpoints = SimpleNamespace(
        list_checkpoints=lambda *, task_id=None: cps,
        get_snapshot=lambda checkpoint_id: snapshots[checkpoint_id],
    )
    modes: list[str] = []
    _patch_runtime(monkeypatch, orch, checkpoints=checkpoints, registry=_registry_stub(modes))

    rc = main(["task", "--resume", "t1"])

    assert rc == 0
    assert orch.calls["session_id"] == "orig-sess"  # 复用检查点会话（同一任务不分裂）
    assert modes == []  # 续跑不铸新会话


def test_task_resume_legacy_default_session_unattributed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """旧占位值检查点：视作未归属 + stderr 明示提示（不迁移旧数据）。"""
    orch = _StreamOrchestrator([("task_started", {}), ("task_finished", {"outcomes": []})])
    plan = Plan(
        subtasks=[Subtask(id="1", goal="g", acceptance="")], goal="g", order=["1"], waves=[["1"]]
    )
    cps = [SimpleNamespace(checkpoint_id="cp1", task_id="t1", session_id="default", ts=1.0)]
    snapshots = {"cp1": SimpleNamespace(state={"plan": plan_to_dict(plan), "done": False})}
    checkpoints = SimpleNamespace(
        list_checkpoints=lambda *, task_id=None: cps,
        get_snapshot=lambda checkpoint_id: snapshots[checkpoint_id],
    )
    _patch_runtime(monkeypatch, orch, checkpoints=checkpoints, registry=_registry_stub([]))

    rc = main(["task", "--resume", "t1"])

    assert rc == 0
    assert orch.calls["session_id"] == ""
    captured = capsys.readouterr()
    assert "未携带会话" in captured.err  # 明示提示（不静默）


# ---- task/serve 启动呈现未完成任务 + 续跑取最新检查点（change 0191 / 账本 E128）----


def test_task_surfaces_incomplete_tasks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """新任务启动扫描检查点 → 呈现未完成任务（只呈现不重执行）。"""
    orch = _StreamOrchestrator([("task_started", {}), ("task_finished", {"outcomes": []})])
    handles = [SimpleNamespace(task_id="old-task"), SimpleNamespace(task_id="old-task2")]
    _patch_runtime(
        monkeypatch, orch, checkpoints=None, registry=_registry_stub([]), handles=handles
    )

    rc = main(["task", "新目标", "--task-id", "t1"])

    assert rc == 0
    err = capsys.readouterr().err
    assert "2 个未完成任务" in err
    assert "task --resume old-task" in err and "task --resume old-task2" in err
    assert orch.calls["task_id"] == "t1"  # 只执行本次请求的任务，不自动续跑未完成任务


def test_task_no_incomplete_is_silent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """空库启动：无未完成任务 → 无呈现（静默）。"""
    orch = _StreamOrchestrator([("task_started", {}), ("task_finished", {"outcomes": []})])
    _patch_runtime(monkeypatch, orch, checkpoints=None, registry=_registry_stub([]), handles=[])

    rc = main(["task", "g", "--task-id", "t1"])

    assert rc == 0
    assert "未完成任务" not in capsys.readouterr().err


def test_task_resume_latest_by_ts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """续跑取**时间戳最新**检查点（落盘序 ≠ 时间序时不取末元素）。"""
    newer = Plan(
        subtasks=[Subtask(id="n", goal="newer", acceptance="")],
        goal="新",
        order=["n"],
        waves=[["n"]],
    )
    older = Plan(
        subtasks=[Subtask(id="o", goal="older", acceptance="")],
        goal="旧",
        order=["o"],
        waves=[["o"]],
    )
    # 落盘序：cp_old 在后（cps[-1] == cp_old），但 ts 更早 ⇒ 必须取 cp_new
    cps = [
        SimpleNamespace(checkpoint_id="cp_new", task_id="t1", session_id="s", ts=2.0),
        SimpleNamespace(checkpoint_id="cp_old", task_id="t1", session_id="s", ts=1.0),
    ]
    snapshots = {
        "cp_new": SimpleNamespace(state={"plan": plan_to_dict(newer), "done": False}),
        "cp_old": SimpleNamespace(state={"plan": plan_to_dict(older), "done": False}),
    }
    checkpoints = SimpleNamespace(
        list_checkpoints=lambda *, task_id=None: cps,
        get_snapshot=lambda checkpoint_id: snapshots[checkpoint_id],
    )
    orch = _StreamOrchestrator([("task_started", {}), ("task_finished", {"outcomes": []})])
    _patch_runtime(monkeypatch, orch, checkpoints=checkpoints)

    rc = main(["task", "--resume", "t1"])

    assert rc == 0
    assert orch.calls["goal"] == "新"  # 取 ts 最新检查点重建的目标


def test_serve_surfaces_incomplete_tasks(monkeypatch, tmp_path, capsys) -> None:
    """serve 启动呈现未完成任务（真 runtime + 落盘检查点，change 0191）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    store = CheckpointStore(state_dir / "checkpoints.jsonl")
    CheckpointManager(store).create_checkpoint("stale-task", "s", {"done": False})

    captured: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, api=None, serve_impl=None) -> None:
            captured["api"] = api

        def serve(self, host: str, port: int) -> None:
            return None

    monkeypatch.setattr("core.entry.WebBridge", _FakeBridge)
    assert main(["--config", _write_config(tmp_path), "serve"]) == 0

    err = capsys.readouterr().err
    assert "未完成任务" in err and "task --resume stale-task" in err


# ---- time-travel：时间旅行回滚入口（change 0144 / 账本 E73）----


class _FakeTimeTravel:
    """时间旅行桩：记录回滚请求（反回归「`rollback` 无生产调用方」）。"""

    def __init__(self, state: dict[str, object] | None = None) -> None:
        self.calls: list[str] = []
        self._state = {"trace_ids": ["t1", "t2"], "done": False} if state is None else state

    def rollback(self, checkpoint_id: str) -> SimpleNamespace:
        self.calls.append(checkpoint_id)
        return SimpleNamespace(checkpoint_id=checkpoint_id, state=self._state)


def test_time_travel_delegates_to_runtime(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`time-travel <cp>` 委派到 `runtime.time_travel.rollback`，回执含检查点 + 撤销集规模。"""
    travel = _FakeTimeTravel()
    _patch_runtime(monkeypatch, _StreamOrchestrator([]), checkpoints=None, time_travel=travel)

    rc = main(["time-travel", "cp1"])

    assert rc == 0
    assert travel.calls == ["cp1"]  # 生产调用方存在（E73 死面销账）
    out = capsys.readouterr().out
    assert "cp1" in out
    assert "撤销 trace 2 条" in out


def test_time_travel_unknown_checkpoint_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """未知检查点 ⇒ `CHECKPOINT_NOT_FOUND` 转 stderr + 退出码 1（不伪造成功）。"""

    class _Missing(_FakeTimeTravel):
        def rollback(self, checkpoint_id: str) -> SimpleNamespace:
            raise DurabilityError(
                DurabilityErrorCode.CHECKPOINT_NOT_FOUND, f"检查点不存在: {checkpoint_id}"
            )

    _patch_runtime(monkeypatch, _StreamOrchestrator([]), checkpoints=None, time_travel=_Missing())

    rc = main(["time-travel", "ghost"])

    assert rc == 1
    assert "回滚失败" in capsys.readouterr().err


def test_time_travel_rolls_back_persisted_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """跨进程：检查点落盘可寻址 ⇒ 真子进程 `time-travel` 回滚成功（生产入口端到端）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    store = CheckpointStore(_state_path("checkpoints.jsonl"))
    checkpoint = CheckpointManager(store).create_checkpoint(
        "t1", "default", {"trace_ids": ["t1"], "step": 1}
    )

    result = _cli("--config", _write_config(tmp_path), "time-travel", checkpoint.checkpoint_id)

    assert result.returncode == 0, result.stderr
    assert checkpoint.checkpoint_id in result.stdout


def test_memory_maintain_runs_maintenance(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`memory maintain`：装配 runtime → 触发一次记忆维护并打印归档条数。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    called: list[str] = []

    class _FakeMemory:
        def compact(self, query: str = "", budget: int = 4096) -> None:
            called.append("compact")

        def forget(self, *, threshold: float = 0.0) -> list[str]:
            called.append("forget")
            return ["stale-1", "stale-2"]

    class _FakeRuntime:
        memory = _FakeMemory()

    monkeypatch.setattr("core.entry.build_runtime", lambda *a, **kw: _FakeRuntime())
    assert main(["--config", _write_config(tmp_path), "memory", "maintain"]) == 0
    assert called == ["compact", "forget"]
    assert "2" in capsys.readouterr().out


def test_memory_maintain_reports_build_failure(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """装配失败 → stderr 提示 + 退出码 1（与 run/serve 同构）。"""

    def _boom(*a, **kw):
        raise RuntimeError("配置缺失")

    monkeypatch.setattr("core.entry.build_runtime", _boom)
    assert main(["--config", _write_config(tmp_path), "memory", "maintain"]) == 1
    assert "装配失败" in capsys.readouterr().err


def test_evolve_run_triggers_cold_path(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`evolve run`：装配 runtime → 强制跑一轮冷路径并打印结局。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    calls: list[bool] = []

    class _FakeEvolution:
        def maybe_run(self, *, force: bool = False, goal: str | None = None) -> object:
            calls.append(force)
            return type("_O", (), {"status": "no_evidence", "skill_id": None})()

    class _FakeRuntime:
        evolution = _FakeEvolution()

    monkeypatch.setattr("core.entry.build_runtime", lambda *a, **kw: _FakeRuntime())
    assert main(["--config", _write_config(tmp_path), "evolve", "run"]) == 0
    assert calls == [True], "显式入口跳过阈值门"
    out = capsys.readouterr().out
    assert "no_evidence" in out


def test_evolve_run_forwards_explicit_goal(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`evolve run --goal X`：显式目标透传到冷路径并回显（人不猜「谁会被选中」）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen: list[str | None] = []

    class _FakeEvolution:
        def maybe_run(self, *, force: bool = False, goal: str | None = None) -> object:
            seen.append(goal)
            return type("_O", (), {"status": "no_evidence", "skill_id": None})()

    class _FakeRuntime:
        evolution = _FakeEvolution()

    monkeypatch.setattr("core.entry.build_runtime", lambda *a, **kw: _FakeRuntime())
    argv = ["--config", _write_config(tmp_path), "evolve", "run", "--goal", "tools.web_fetch"]

    assert main(argv) == 0
    assert seen == ["tools.web_fetch"]
    assert "本轮目标：tools.web_fetch" in capsys.readouterr().out


def test_evolve_run_reports_build_failure(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """装配失败 → stderr 提示 + 退出码 1。"""

    def _boom(*a, **kw):
        raise RuntimeError("配置缺失")

    monkeypatch.setattr("core.entry.build_runtime", _boom)
    assert main(["--config", _write_config(tmp_path), "evolve", "run"]) == 1
    assert "装配失败" in capsys.readouterr().err


# ---- 会话注册表（change 0094：CLI 跨进程可见 / 枚举 / 端到端 run） ----


class _FixedLoop:
    """产出固定事件流的 loop 替身（不出网）。"""

    async def astream(self, user_input: str, *, session_id: str = ""):
        yield LoopEvent("loop_started", {"trace_id": "t1"})
        yield LoopEvent("loop_finished", {"reply": "pong"})


def _patch_fake_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """装配替身 runtime：四入口共用 `_build_ui` 只取 loop/memory/tools/app.llm。"""
    runtime = SimpleNamespace(
        loop=_FixedLoop(),
        memory=None,
        tools=None,
        config=None,
        orchestrator=None,
        pet_activator=None,
        pet_manager=None,
        beast_activator=None,  # change 0137：`_build_ui` 读该字段
        transcript=None,  # change 0115：`_build_ui` 读该字段；None ⇒ 读取面逐字保持原形状
        recover=lambda: [],  # change 0207：入口启动扫描调 `runtime.recover()`；空 ⇒ 静默
        app=SimpleNamespace(
            llm=LLMConfig(
                provider="openai", model="gpt-4o", endpoint="https://x", api_key_ref="${K}"
            )
        ),
    )
    monkeypatch.setattr("core.entry.build_runtime", lambda *a, **kw: runtime)


def test_session_create_writes_shared_registry(capsys: pytest.CaptureFixture[str]) -> None:
    """`session create` 落共享注册表（非进程内存）⇒ 他进程可读。"""
    assert main(["session", "create"]) == 0
    session_id = capsys.readouterr().out.strip()

    assert SessionRegistry(path=_state_path("conversations.json")).exists(session_id)


def test_session_list_shows_created(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["session", "create"]) == 0
    session_id = capsys.readouterr().out.strip()

    assert main(["session", "list"]) == 0
    assert session_id in capsys.readouterr().out


def test_session_list_empty(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["session", "list"]) == 0
    assert "无对话会话" in capsys.readouterr().out


def test_run_sees_cli_created_session_in_other_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """端到端：`session create` 建 id → 另一次 `run --session <id>` 认它（不再 not found）。"""
    _patch_fake_runtime(monkeypatch)
    assert main(["session", "create"]) == 0
    session_id = capsys.readouterr().out.strip()

    rc = main(
        [
            "--config",
            str(tmp_path / "missing.yaml"),
            "run",
            "--session",
            session_id,
            "--prompt",
            "hi",
        ]
    )

    assert rc == 0
    assert "[session.created]" in capsys.readouterr().out


def test_run_unknown_session_still_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """反例：未登记 id 仍 fail-closed（持久化不放宽校验）。"""
    _patch_fake_runtime(monkeypatch)

    rc = main(
        ["--config", str(tmp_path / "missing.yaml"), "run", "--session", "nope", "--prompt", "hi"]
    )

    assert rc == 1
    assert "运行失败" in capsys.readouterr().err


def test_session_show_prints_transcript(capsys: pytest.CaptureFixture[str]) -> None:
    """`session show`：按追加次序打印该会话转录（与内核回灌同一存储）。"""
    assert main(["session", "create"]) == 0
    session_id = capsys.readouterr().out.strip()
    store = TranscriptStore(path=_state_path("messages.jsonl"))
    store.append(session_id, "user", "第一问")
    store.append(session_id, "assistant", "第一答")

    assert main(["session", "show", session_id]) == 0

    out = capsys.readouterr().out
    assert "第一问" in out
    assert "第一答" in out
    assert out.index("第一问") < out.index("第一答")


def test_session_show_without_transcript(capsys: pytest.CaptureFixture[str]) -> None:
    """无转录的会话：明示无记录、退出码 0（不伪造内容）。"""
    assert main(["session", "create"]) == 0
    session_id = capsys.readouterr().out.strip()

    assert main(["session", "show", session_id]) == 0

    assert "无对话记录" in capsys.readouterr().out


def test_session_show_unknown_session_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    """反例：未登记 id 的转录读取 fail-closed（不放宽会话校验）。"""
    assert main(["session", "show", "nope"]) == 1
    assert "nope" in capsys.readouterr().err


def test_repl_resumes_session_via_flag(monkeypatch, tmp_path) -> None:
    """顶层 `--session <id>`：交互入口续接既有会话（标识透传至 CLIBridge）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, api=None, connect_impl=None, session_id="") -> None:
            captured["api"] = api
            captured["session_id"] = session_id

        def connect(self) -> None:
            return None

    monkeypatch.setattr("core.entry.CLIBridge", _FakeBridge)
    session_id = SessionRegistry(path=_state_path("conversations.json")).create("cli")

    assert main(["--config", _write_config(tmp_path), "--session", session_id]) == 0
    assert captured["session_id"] == session_id


def test_repl_without_flag_passes_empty_session(monkeypatch, tmp_path) -> None:
    """缺省不指定 `--session`：透传空串（由 repl 新建会话，既有行为不变）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, api=None, connect_impl=None, session_id="") -> None:
            captured["session_id"] = session_id

        def connect(self) -> None:
            return None

    monkeypatch.setattr("core.entry.CLIBridge", _FakeBridge)

    assert main(["--config", _write_config(tmp_path)]) == 0
    assert captured["session_id"] == ""


def test_run_stream_skips_reasoning_frames(capsys: pytest.CaptureFixture[str]) -> None:
    """思考回显不逐段刷屏：`loop.reasoning` 与 `loop.delta` 同处置（change 0145 / 账本 E56~E60）。

    非交互 `core-agent run` 无折叠块可承载思考原文 ⇒ 逐段打印只会刷屏；完整回复由终态
    `loop.result` 携带（与 `loop.delta` 同判据）。
    """
    import asyncio  # noqa: PLC0415 — 驱动异步 `_stream`

    from core.entry import _stream  # noqa: PLC0415 — 内部流式打印口径
    from core.ui import Event  # noqa: PLC0415 — 事件构造

    class _Api:
        async def run_loop(self, session_id: str, prompt: str):
            yield Event(type="loop.delta", payload={"text": "你"})
            yield Event(type="loop.reasoning", payload={"text": "内部草稿"})
            yield Event(type="loop.result", payload="好了")

    asyncio.run(_stream(_Api(), "s", "hi"))  # type: ignore[arg-type]
    out = capsys.readouterr().out
    assert "内部草稿" not in out
    assert "你" not in out
    assert "[loop.result] 好了" in out


# ---- notes：常驻标记 CLI（change 0149 / ADR-0141 / 账本 E93） ----


def _seed_note(note_id: str, *, title: str, content: str, pinned: bool = False) -> None:
    """以组合根同源路径播种一篇 canonical 笔记（`CORE_STATE_DIR` 由 conftest 隔离）。"""
    NoteStore(path=_state_path("notes")).update(
        NoteEntry(note_id=note_id, title=title, content=content, pinned=pinned)
    )


def test_notes_pin_then_show_marks_pinned(capsys: pytest.CaptureFixture[str]) -> None:
    """pin 落盘 ⇒ 跨实例（新进程语义）读回 ⇒ `notes show` 显示 `- pinned: true`。"""
    _seed_note("约束", title="硬约束", content="接口必须 HTTPS")

    assert main(["notes", "pin", "约束"]) == 0
    assert NoteStore(path=_state_path("notes")).get("约束").pinned is True, "落盘真源"

    assert main(["notes", "show", "约束"]) == 0
    assert "- pinned: true" in capsys.readouterr().out

    assert main(["notes", "unpin", "约束"]) == 0
    assert NoteStore(path=_state_path("notes")).get("约束").pinned is False


def test_notes_pin_missing_note_returns_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["notes", "pin", "不存在"]) == 1
    assert "NOTE_NOT_FOUND" in capsys.readouterr().err


def test_notes_pin_is_idempotent() -> None:
    """同值重复 pin ⇒ 不写盘（`updated_at` 不变），两次均成功退出。"""
    _seed_note("约束", title="硬约束", content="接口必须 HTTPS")

    assert main(["notes", "pin", "约束"]) == 0
    first = NoteStore(path=_state_path("notes")).get("约束").updated_at
    assert main(["notes", "pin", "约束"]) == 0
    assert NoteStore(path=_state_path("notes")).get("约束").updated_at == first


def test_notes_list_marks_pinned(capsys: pytest.CaptureFixture[str]) -> None:
    _seed_note("约束", title="硬约束", content="必须 HTTPS", pinned=True)
    _seed_note("其他", title="其他", content="无关")

    assert main(["notes", "list"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    pinned_line = next(line for line in lines if line.startswith("约束"))
    other_line = next(line for line in lines if line.startswith("其他"))
    assert pinned_line.endswith("\t[pinned]")
    assert not other_line.endswith("[pinned]"), "非常驻行输出不变"


def test_notes_usage_lists_pin_verbs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["notes"]) == 1
    err = capsys.readouterr().err
    assert "pin <note_id>" in err and "unpin <note_id>" in err


def test_notes_pin_with_priority_persists(capsys: pytest.CaptureFixture[str]) -> None:
    """`notes pin --priority` 落盘；`unpin` 归零（change 0154 / 路线图 G1）。"""
    _seed_note("约束", title="硬约束", content="接口必须 HTTPS")

    assert main(["notes", "pin", "约束", "--priority", "5"]) == 0
    assert NoteStore(path=_state_path("notes")).get("约束").pin_priority == 5, "落盘真源"  # noqa: PLR2004
    raw = (_state_path("notes") / "约束.md").read_text(encoding="utf-8")
    assert "- pin_priority: 5" in raw

    assert main(["notes", "unpin", "约束"]) == 0
    assert NoteStore(path=_state_path("notes")).get("约束").pin_priority == 0


def test_notes_pinned_reports_in_context_and_overflow(capsys: pytest.CaptureFixture[str]) -> None:
    """`notes pinned` 报出「在场 / 未进场」（超常驻预算篇目不再静默）。"""
    _seed_note("keep", title="K", content="x" * 100, pinned=True)
    _seed_note("drop", title="D", content="y" * 4000, pinned=True)
    NoteStore(path=_state_path("notes")).set_pinned("keep", pinned=True, priority=5)

    assert main(["notes", "pinned"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    keep = next(line for line in lines if line.startswith("keep"))
    drop = next(line for line in lines if line.startswith("drop"))
    assert "[在场]" in keep, "高优先级整篇在场"
    assert "[未进场]" in drop, "超预算篇整篇排除且可见"


# ---- notes：会话摘要提升（change 0150 / ADR-0142 / 账本 E94） ----


def _seed_summary(session_id: str, content: str) -> None:
    """以组合根同源路径播种一条会话压实摘要（`CORE_STATE_DIR` 由 conftest 隔离）。"""
    key = session_id or "default"
    MemoryStore(backend=FileBackend(_state_path("memory.jsonl"))).write(
        "L2",
        MemoryEntry(
            id=f"compaction.summary.{key}",
            layer="L2",
            content=content,
            tags=["compaction", "summary"],
            source="compaction",
            trace_id=f"compaction.{key}",
            session_id=session_id,
            kind="semantic",
        ),
    )


def test_notes_promote_writes_note_and_show_reads_it(capsys: pytest.CaptureFixture[str]) -> None:
    """提升落盘 ⇒ 跨进程（新 CLI 调用）读回：正文含摘要、常驻标记可见。"""
    _seed_summary("sess-7", "结论：对外接口必须 HTTPS")

    assert main(["notes", "promote", "sess-7"]) == 0
    assert capsys.readouterr().out.strip(), "提升须有回执"

    assert main(["notes", "show", "session-sess-7"]) == 0
    out = capsys.readouterr().out
    assert "对外接口必须 HTTPS" in out
    assert "- pinned: true" in out
    assert "notes.promote" in out


def test_notes_promote_missing_summary_returns_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["notes", "promote", "无摘要会话"]) == 1
    assert capsys.readouterr().err.strip(), "缺失摘要须有明确报错"
    assert list(_state_path("notes").glob("*.md")) == [], "不写任何文件"


def test_notes_promote_idempotent_across_processes(capsys: pytest.CaptureFixture[str]) -> None:
    """同会话重复提升 ⇒ 仍单条（覆盖式），内容为第二次。"""
    _seed_summary("s1", "第一次结论")
    assert main(["notes", "promote", "s1"]) == 0

    _seed_summary("s1", "第二次结论")
    assert main(["notes", "promote", "s1"]) == 0
    capsys.readouterr()

    notes_dir = _state_path("notes")
    assert len(list(notes_dir.glob("session-*.md"))) == 1, "不增长"
    assert main(["notes", "show", "session-s1"]) == 0
    out = capsys.readouterr().out
    assert "第二次结论" in out and "第一次结论" not in out


def test_notes_promote_marks_pinned(capsys: pytest.CaptureFixture[str]) -> None:
    _seed_summary("s1", "结论：X")
    assert main(["notes", "promote", "s1"]) == 0
    capsys.readouterr()

    assert main(["notes", "list"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert any(line.startswith("session-s1") and line.endswith("\t[pinned]") for line in lines)


def test_notes_usage_lists_promote_verb(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["notes"]) == 1
    assert "promote <session-id>" in capsys.readouterr().err


def test_notes_promote_refuses_foreign_source_note(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """派生 id 撞人工笔记（未给 `--as`）⇒ 非零退出、canonical 文件**逐字不变**（来源守护）。"""
    _seed_summary("s1", "结论：X")
    notes_dir = _state_path("notes")
    notes_dir.mkdir(parents=True, exist_ok=True)
    target = notes_dir / "session-s1.md"
    target.write_text(
        "# 人工主题\n\n- id: session-s1\n- source: notes\n\n## Notes\n\n人工正文\n",
        encoding="utf-8",
    )
    before = target.read_text(encoding="utf-8")

    assert main(["notes", "promote", "s1"]) == 1
    assert capsys.readouterr().err.strip(), "撞车须有明确报错"
    assert target.read_text(encoding="utf-8") == before, "人工笔记逐字不变"
    assert len(list(notes_dir.glob("session-*.md"))) == 1, "不产生第二条"


# ---- 只读诊断面（change 0162：doctor / status 真诊断） ----


def test_doctor_exits_zero_when_all_green(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """场景「自检全绿」：配置有效 + 密钥引用可解析 ⇒ 逐项列出且退出码 0。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ENTRY-CANARY")
    assert main(["--config", _write_config(tmp_path), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "自检诊断" in out
    assert "✓" in out
    assert "sk-ENTRY-CANARY" not in out, "密钥值不得出现在诊断输出"


def test_doctor_exits_nonzero_on_unresolvable_secret(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """场景「存在失败项时非零退出」：引用不可解析 ⇒ 非零退出，且写明是哪一项（不出取值）。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["--config", _write_config(tmp_path), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "✗ 配置" in out
    assert "llm.api_key" in out
    assert "sk-test" not in out


def test_status_overview_exits_zero(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """场景「运行状态概览」：六项字段打印且恒 0；输出不含密钥值。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ENTRY-CANARY")
    assert main(["--config", _write_config(tmp_path), "status"]) == 0
    out = capsys.readouterr().out
    for label in ("会话数", "内置工具", "已安装资产", "MCP 端点", "模型", "循环预算"):
        assert label in out
    assert "sk-ENTRY-CANARY" not in out


def test_status_with_unreadable_config_still_exits_zero(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`status` 是信息面不是判据：配置不可用时如实标注，仍恒 0（与 doctor 的分工）。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["--config", _write_config(tmp_path), "status"]) == 0
    assert "会话数" in capsys.readouterr().out


# ---- 恢复扫描入口全覆盖（change 0207 / 台账 E144） ----


def _seed_incomplete(state_dir: pathlib.Path, task_id: str = "task-stale") -> None:
    """在隔离状态目录放一个未完成任务检查点（done=False），供恢复扫描呈现用例使用。

    只写扫描读取的字段（``state["done"]``）；``restore`` 只需快照存在即可返回句柄。
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    CheckpointManager(CheckpointStore(state_dir / "checkpoints.jsonl")).create_checkpoint(
        task_id, "sess-1", {"done": False}
    )


class _NoopCLIBridge:
    def __init__(self, *, api=None, connect_impl=None, session_id="") -> None:
        pass

    def connect(self) -> None:
        return None


class _NoopDesktopBridge:
    def __init__(self, *, api=None, start_impl=None, port=None) -> None:
        pass

    def start_sidecar(self) -> None:
        return None


class _NoopMCPServer:
    def __init__(self, *, tool_provider=None, whitelist=None) -> None:
        pass

    def serve_stdio(self, endpoint) -> None:
        return None


async def _noop_stream(api, session_id: str, prompt: str) -> None:
    return None


@pytest.mark.parametrize(
    "argv",
    [[], ["run", "--prompt", "hi"], ["app"], ["mcp", "serve"]],
    ids=["repl", "run", "app", "mcp-serve"],
)
def test_recovery_surface_on_all_interactive_entries(
    argv, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """四入口启动均在 stderr 呈现未完成任务 + 续跑提示（只报 task id，change 0207）。"""
    state_dir = tmp_path / "state"
    _seed_incomplete(state_dir)
    monkeypatch.setenv("CORE_STATE_DIR", str(state_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("core.entry.CLIBridge", _NoopCLIBridge)
    monkeypatch.setattr("core.entry.DesktopBridge", _NoopDesktopBridge)
    monkeypatch.setattr("core.entry.MCPServer", _NoopMCPServer)
    monkeypatch.setattr("core.entry._stream", _noop_stream)

    assert main(["--config", _write_config(tmp_path), *argv]) == 0
    err = capsys.readouterr().err
    assert "未完成任务" in err
    assert "task --resume task-stale" in err


@pytest.mark.parametrize("argv", [[], ["mcp", "serve"]], ids=["repl", "mcp-serve"])
def test_recovery_surface_silent_without_stale_tasks(
    argv, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """无未完成任务 ⇒ 启动静默（不打印告警；`_surface_incomplete` 提前返回）。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("core.entry.CLIBridge", _NoopCLIBridge)
    monkeypatch.setattr("core.entry.MCPServer", _NoopMCPServer)

    assert main(["--config", _write_config(tmp_path), *argv]) == 0
    assert "未完成任务" not in capsys.readouterr().err
