"""entry 单元测试（对齐契约红线：命令面 / 三级帮助 / 未知命令错误码 / 版本输出）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.deployment import ServeStateStore
from core.entry import _build_installer, _build_parser, main
from core.loop import LoopEvent
from core.orchestration import Plan, Subtask, plan_to_dict

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


def test_repl_wires_llm_config(monkeypatch, tmp_path) -> None:
    """无子命令进 REPL：真 runtime 装配 + 注入 LLM 配置（对齐 run 的同构入口）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict[str, object] = {}

    class _FakeBridge:
        def __init__(self, *, api=None, connect_impl=None) -> None:
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
        def __init__(self, *, api=None, start_impl=None) -> None:
            captured["api"] = api

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


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch, orch: _StreamOrchestrator, checkpoints: object
) -> None:
    runtime = SimpleNamespace(orchestrator=orch, checkpoints=checkpoints)
    monkeypatch.setattr("core.entry.build_runtime", lambda config: runtime)


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
    _patch_runtime(monkeypatch, orch, checkpoints=None)

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
    _patch_runtime(monkeypatch, orch, checkpoints=None)

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
    cps = [SimpleNamespace(checkpoint_id="cp1", task_id="t1")]
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
        def maybe_run(self, *, force: bool = False) -> object:
            calls.append(force)
            return type("_O", (), {"status": "no_evidence", "skill_id": None})()

    class _FakeRuntime:
        evolution = _FakeEvolution()

    monkeypatch.setattr("core.entry.build_runtime", lambda *a, **kw: _FakeRuntime())
    assert main(["--config", _write_config(tmp_path), "evolve", "run"]) == 0
    assert calls == [True], "显式入口跳过阈值门"
    out = capsys.readouterr().out
    assert "no_evidence" in out


def test_evolve_run_reports_build_failure(
    monkeypatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """装配失败 → stderr 提示 + 退出码 1。"""

    def _boom(*a, **kw):
        raise RuntimeError("配置缺失")

    monkeypatch.setattr("core.entry.build_runtime", _boom)
    assert main(["--config", _write_config(tmp_path), "evolve", "run"]) == 1
    assert "装配失败" in capsys.readouterr().err
