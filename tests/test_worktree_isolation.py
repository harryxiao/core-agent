"""子 Agent 工作树隔离用例（change 0284 / ADR-0274）。

前半：git 原语之上的管理器与工作区上下文；后半（接线就绪后）：委托隔离、后台登记、
权限分级与工具面。全部操作在 `tmp_path` 的临时仓库内完成，绝不在当前仓库写文件。
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.loop import LoopResult, current_session_id
from core.orchestration import (
    BackgroundAgentRegistry,
    BackgroundTaskInfo,
    OrchestrationError,
    OrchestrationErrorCode,
    WorktreeManager,
)
from core.permission import (
    AccessControlError,
    PermissionMode,
    PermissionModeGate,
    PolicyEngine,
    RiskLevel,
)
from core.runtime import build_runtime
from core.tools import ToolErrorCode
from core.tools.builtin import code_run, file_write
from core.tools.workspace import resolve_path, use_workspace, workspace_root

_SIDECAR_MODE = 0o600
_ROOT_MODE = 0o700


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """建一个有一次提交的临时仓库，返回仓库根。"""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "tester@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "tester@example.com")
    root = tmp_path / "repo"
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    monkeypatch.chdir(root)  # 缺省仓库发现必须落在临时仓库，绝不碰真实仓库
    return root


def _manager(tmp_path: Path) -> WorktreeManager:
    return WorktreeManager(tmp_path / "state" / "worktrees")


def _branch_list(root: Path) -> str:
    return subprocess.run(
        ["git", "branch", "--list"], cwd=root, check=True, capture_output=True, text=True
    ).stdout


# ---- 管理器 ----


def test_manager_creates_worktree_branch_and_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)

    lease = manager.create(agent_id="coding")

    assert Path(lease.path).is_dir()
    assert (Path(lease.path) / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert lease.branch in _branch_list(repo)
    sidecar = Path(lease.path).with_suffix(".json")
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    assert record["id"] == lease.worktree_id
    assert not {"task", "session_id", "reply"} & set(record)
    if os.name == "posix":
        assert stat.S_IMODE(sidecar.stat().st_mode) == _SIDECAR_MODE
        assert stat.S_IMODE(manager.root.stat().st_mode) == _ROOT_MODE


def test_manager_rejects_non_git_repo(tmp_path: Path) -> None:
    manager = _manager(tmp_path)

    with pytest.raises(OrchestrationError) as caught:
        manager.create(agent_id="coding", start=tmp_path)

    assert caught.value.code is OrchestrationErrorCode.WORKTREE_UNAVAILABLE
    assert not manager.root.exists()


def test_manager_rejects_state_root_inside_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    manager = WorktreeManager(repo / "state")

    with pytest.raises(OrchestrationError) as caught:
        manager.create(agent_id="coding", start=repo)

    assert caught.value.code is OrchestrationErrorCode.WORKTREE_UNAVAILABLE


def test_manager_rejects_repo_without_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "empty"
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    manager = _manager(tmp_path)

    with pytest.raises(OrchestrationError) as caught:
        manager.create(agent_id="coding", start=root)

    assert caught.value.code is OrchestrationErrorCode.WORKTREE_UNAVAILABLE
    assert not manager.root.exists() or not list(manager.root.glob("*/*"))


def test_manager_discard_removes_worktree_branch_and_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)
    lease = manager.create(agent_id="coding")
    sidecar = Path(lease.path).with_suffix(".json")

    assert manager.discard(lease.worktree_id)["ok"] is True

    assert not Path(lease.path).exists()
    assert not sidecar.exists()
    assert lease.branch not in _branch_list(repo)
    again = manager.discard(lease.worktree_id)
    assert again["ok"] is True and again["removed"] is False


def test_manager_discard_rejects_tampered_sidecar_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)
    lease = manager.create(agent_id="coding")
    other = manager.create(agent_id="coding")
    sidecar = Path(lease.path).with_suffix(".json")
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    # 把 A 的登记指向另一个合法工作树 B：校验缺失时 B 会被删除、A 的登记被误导清理。
    record["path"] = other.path
    sidecar.write_text(json.dumps(record), encoding="utf-8")

    result = manager.discard(lease.worktree_id)

    assert result["ok"] is False
    assert Path(other.path).exists()
    assert Path(lease.path).exists()
    assert sidecar.exists()


def test_manager_discard_dirty_requires_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)
    lease = manager.create(agent_id="coding")
    (Path(lease.path) / "dirty.txt").write_text("unsaved\n", encoding="utf-8")

    refused = manager.discard(lease.worktree_id)

    assert refused["ok"] is False
    assert Path(lease.path).exists()
    assert manager.discard(lease.worktree_id, force=True)["ok"] is True
    assert not Path(lease.path).exists()


def test_manager_list_skips_corrupt_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)
    lease = manager.create(agent_id="coding")
    corrupt = Path(lease.path).parent / "wt-000000000000.json"
    corrupt.write_text("not json", encoding="utf-8")

    listing = manager.list()

    assert [item["id"] for item in listing["worktrees"]] == [lease.worktree_id]
    assert listing["truncated"] is False


# ---- 工作区上下文 ----


def test_resolve_path_relative_absolute_and_tilde(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    root = tmp_path / "ws"

    assert resolve_path("a.txt") == Path("a.txt")
    with use_workspace(root):
        assert resolve_path("a.txt") == root / "a.txt"
        assert resolve_path("/abs/a.txt") == Path("/abs/a.txt")
        assert resolve_path("~/x.txt") == home / "x.txt"
        assert workspace_root() == root
    assert workspace_root() is None


def test_file_write_lands_in_worktree_not_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)
    lease = manager.create(agent_id="coding")

    with use_workspace(lease.path):
        file_write().handler("out.txt", "isolated\n")

    assert (Path(lease.path) / "out.txt").read_text(encoding="utf-8") == "isolated\n"
    assert not (repo / "out.txt").exists()


def test_code_run_defaults_to_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)
    lease = manager.create(agent_id="coding")
    tool = code_run()

    with use_workspace(lease.path):
        default = asyncio.run(tool.handler(script="import os; print(os.getcwd())", type="python"))

    assert Path(default["stdout"].strip()).resolve() == Path(lease.path).resolve()
    assert default["returncode"] == 0


def test_code_run_explicit_relative_cwd_is_worktree_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path, monkeypatch)
    manager = _manager(tmp_path)
    lease = manager.create(agent_id="coding")
    (Path(lease.path) / "sub").mkdir()
    tool = code_run()

    with use_workspace(lease.path):
        result = asyncio.run(
            tool.handler(script="import os; print(os.getcwd())", type="python", cwd="sub")
        )

    assert Path(result["stdout"].strip()).resolve() == (Path(lease.path) / "sub").resolve()
    assert result["returncode"] == 0


def test_worktree_starts_from_head_ignoring_dirty_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    (repo / "scratch.txt").write_text("main dirt\n", encoding="utf-8")
    manager = _manager(tmp_path)

    lease = manager.create(agent_id="coding")

    assert (Path(lease.path) / "a.txt").exists()
    assert not (Path(lease.path) / "scratch.txt").exists()


# ---- 配置 ----


_LLM_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
"""
_ISOLATION_YAML = "orchestration:\n  worktree_isolation: true\n"


def _cfg(tmp_path: Path, extra: str = "") -> ConfigManager:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(_LLM_YAML + extra, encoding="utf-8")
    manager = ConfigManager(yaml_path=cfg, environ={"OPENAI_API_KEY": "sk-test"})
    manager.load()
    return manager


def test_worktree_isolation_spec_and_default_off(tmp_path: Path) -> None:
    spec = {item.key: item for item in config_specs()}["orchestration.worktree_isolation"]

    assert (spec.cli_flag, spec.env_var, spec.map_to, spec.default) == (
        "--orchestration.worktree-isolation",
        "CORE_ORCHESTRATION_WORKTREE_ISOLATION",
        "orchestration.worktree_isolation",
        False,
    )
    assert _cfg(tmp_path).orchestration_worktree_isolation() is False
    enabled = _cfg(tmp_path, _ISOLATION_YAML)
    assert enabled.orchestration_worktree_isolation() is True


def test_worktree_isolation_invalid_blocks_load(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="worktree_isolation"):
        _cfg(tmp_path, "orchestration:\n  worktree_isolation: maybe\n")


# ---- 运行时接线 ----


def _runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cwd: Path,
    enabled: bool = True,
    extra: str = "",
) -> Any:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "home").mkdir(exist_ok=True)
    monkeypatch.chdir(cwd)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        _LLM_YAML + (_ISOLATION_YAML if enabled else "") + extra, encoding="utf-8"
    )
    return build_runtime(ConfigManager(yaml_path=config_path))


def _coding_loop(runtime: Any) -> Any:
    return runtime.orchestrator._router._agents["coding"].loop  # noqa: SLF001


def _git_status(repo: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def test_isolation_off_keeps_existing_delegate_shape_and_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch, cwd=tmp_path, enabled=False)
    coding = _coding_loop(runtime)

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        return LoopResult(reply="同步结果", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)
    tool_ids = {tool.tool_id for tool in runtime.tools.active_tools()}
    assert "tools.worktree.list" not in tool_ids
    assert "tools.worktree.discard" not in tool_ids
    assert runtime.worktrees is None

    async def scenario() -> tuple[Any, BackgroundTaskInfo]:
        fg = await runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        bg = await runtime.tools.ainvoke(
            "tools.delegate", {"task": "写代码", "background": True}, trace_id="t2"
        )
        assert set(cast(dict[str, Any], bg.data)) == {"ok", "task_id", "status", "agent"}
        info = await runtime.background_tasks.wait(cast(dict[str, Any], bg.data)["task_id"])
        return fg, info

    fg, info = asyncio.run(scenario())
    assert fg.data == {"ok": True, "reply": "同步结果"}
    assert info.worktree == {}
    payload = json.loads((tmp_path / "state" / "background-tasks.json").read_text("utf-8"))
    assert all("worktree" not in item for item in payload["tasks"])
    assert not (tmp_path / "state" / "worktrees").exists()


def test_foreground_file_writes_land_in_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        file_write().handler("out.txt", "isolated\n")
        return LoopResult(reply="完成", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    result = asyncio.run(runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1"))

    assert result.ok is True
    data = cast(dict[str, Any], result.data)
    assert data["ok"] is True and data["reply"] == "完成"
    worktree = cast(dict[str, Any], data["worktree"])
    assert Path(worktree["path"], "out.txt").read_text(encoding="utf-8") == "isolated\n"
    assert not (repo / "out.txt").exists()
    assert _git_status(repo) == ""
    assert worktree["changed_files"] == ["out.txt"]
    assert cast(str, worktree["branch"]).startswith("core-agent/wt-")
    assert cast(str, worktree["id"]) in str(worktree["path"])


def test_absolute_path_is_not_remapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)
    target = repo / "absolute.txt"

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        file_write().handler(str(target), "abs\n")
        return LoopResult(reply="完成", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    result = asyncio.run(runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1"))

    worktree = cast(dict[str, Any], cast(dict[str, Any], result.data)["worktree"])
    assert target.read_text(encoding="utf-8") == "abs\n"
    assert not (Path(worktree["path"]) / "absolute.txt").exists()
    assert worktree["changed_files"] == []


def test_background_isolated_persisted_and_notified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        file_write().handler("bg.txt", "后台\n")
        return LoopResult(reply="后台完成", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[str, BackgroundTaskInfo]:
        token = current_session_id.set("s1")
        try:
            result = await runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码", "background": True}, trace_id="t1"
            )
            data = cast(dict[str, Any], result.data)
            assert cast(dict[str, Any], data["worktree"])["id"].startswith("wt-")
            info = await runtime.background_tasks.wait(cast(str, data["task_id"]))
        finally:
            current_session_id.reset(token)
        return cast(str, data["task_id"]), info

    task_id, info = asyncio.run(scenario())
    assert info.status == "done"
    assert info.worktree["changed_files"] == ["bg.txt"]
    assert Path(info.worktree["path"], "bg.txt").read_text(encoding="utf-8") == "后台\n"
    assert not (repo / "bg.txt").exists()

    notice = runtime.background_tasks.render_notices("s1")
    assert f"工作树：{info.worktree['id']}" in notice
    assert cast(str, info.worktree["path"]) not in notice

    state = tmp_path / "state" / "background-tasks.json"
    payload = json.loads(state.read_text(encoding="utf-8"))
    record = next(item for item in payload["tasks"] if item["task_id"] == task_id)
    assert record["worktree"]["id"] == info.worktree["id"]
    assert record["worktree"]["changed_files"] == ["bg.txt"]
    restored = BackgroundAgentRegistry(state_path=state)
    recovered = restored.get(task_id)
    assert recovered is not None
    assert recovered.worktree["id"] == info.worktree["id"]


def test_terminal_retention_and_retry_creates_new_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)
    calls: list[str] = []

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        calls.append(task)
        file_write().handler(f"run{len(calls)}.txt", "x\n")
        if len(calls) == 1:
            raise RuntimeError("boom")
        return LoopResult(reply="重试完成", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[dict[str, Any], str, BackgroundTaskInfo]:
        token = current_session_id.set("s1")
        try:
            first = await runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码", "background": True}, trace_id="t1"
            )
            old_id = cast(str, cast(dict[str, Any], first.data)["task_id"])
            old_info = await runtime.background_tasks.wait(old_id)
        finally:
            current_session_id.reset(token)
        assert old_info.status == "failed"
        retried = await runtime.tools.ainvoke(
            "tools.task_retry", {"task_id": old_id}, trace_id="t2", approved=True
        )
        assert retried.ok is True
        data = cast(dict[str, Any], retried.data)
        assert data["ok"] is True and data["retried"] == old_id
        assert cast(dict[str, Any], data["worktree"])["id"] != old_info.worktree["id"]
        await runtime.background_tasks.wait(cast(str, data["task_id"]))
        return data, old_id, old_info

    data, old_id, old_info = asyncio.run(scenario())
    old_path = Path(cast(str, old_info.worktree["path"]))
    assert old_path.exists(), "终态工作树保留"
    assert old_path.with_suffix(".json").exists()
    new_path = Path(cast(dict[str, Any], data["worktree"])["path"])
    assert (new_path / "run2.txt").exists()
    assert not (new_path / "run1.txt").exists()
    assert (new_path / "run2.txt").read_text(encoding="utf-8") == "x\n"
    assert runtime.background_tasks.get(old_id).status == "failed"  # type: ignore[union-attr]


def test_concurrent_background_delegates_do_not_share_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        await asyncio.sleep(0)
        file_write().handler("same.txt", task)
        return LoopResult(reply=task, trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[BackgroundTaskInfo | None, BackgroundTaskInfo | None]:
        first, second = await asyncio.gather(
            runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码 A", "background": True}, trace_id="t1"
            ),
            runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码 B", "background": True}, trace_id="t2"
            ),
        )
        first_id = cast(str, cast(dict[str, Any], first.data)["task_id"])
        second_id = cast(str, cast(dict[str, Any], second.data)["task_id"])
        await asyncio.gather(
            runtime.background_tasks.wait(first_id), runtime.background_tasks.wait(second_id)
        )
        return runtime.background_tasks.get(first_id), runtime.background_tasks.get(second_id)

    first_info, second_info = asyncio.run(scenario())
    assert first_info is not None and second_info is not None
    assert first_info.worktree["id"] != second_info.worktree["id"]
    assert Path(first_info.worktree["path"], "same.txt").read_text("utf-8") == "写代码 A"
    assert Path(second_info.worktree["path"], "same.txt").read_text("utf-8") == "写代码 B"
    assert _git_status(repo) == ""


def test_non_git_fail_closed_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    runtime = _runtime(tmp_path, monkeypatch, cwd=plain)
    coding = _coding_loop(runtime)
    called: list[str] = []

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        called.append(task)
        return LoopResult(reply="不该执行", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[Any, Any]:
        fg = await runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        bg = await runtime.tools.ainvoke(
            "tools.delegate", {"task": "写代码", "background": True}, trace_id="t2"
        )
        return fg, bg

    fg, bg = asyncio.run(scenario())
    for result in (fg, bg):
        assert result.ok is True
        data = cast(dict[str, Any], result.data)
        assert data["ok"] is False
        assert "WORKTREE_UNAVAILABLE" in cast(str, data["error"])
    assert called == []
    assert runtime.background_tasks.list() == []
    assert not (tmp_path / "state" / "worktrees").exists()


# ---- 工作树工具 ----


def test_worktree_tools_list_and_discard_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        file_write().handler("f.txt", "x\n")
        return LoopResult(reply="ok", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[dict[str, Any], Any, Any, Any, Any]:
        result = await runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        worktree = cast(dict[str, Any], cast(dict[str, Any], result.data)["worktree"])
        listed = await runtime.tools.ainvoke("tools.worktree.list", {}, trace_id="t2")
        denied = await runtime.tools.ainvoke(
            "tools.worktree.discard", {"worktree_id": worktree["id"]}, trace_id="t3"
        )
        discarded = await runtime.tools.ainvoke(
            "tools.worktree.discard",
            {"worktree_id": worktree["id"], "force": True},
            trace_id="t4",
            approved=True,
        )
        again = await runtime.tools.ainvoke(
            "tools.worktree.discard",
            {"worktree_id": worktree["id"]},
            trace_id="t5",
            approved=True,
        )
        return worktree, listed, denied, discarded, again

    worktree, listed, denied, discarded, again = asyncio.run(scenario())
    assert listed.ok is True
    assert [item["id"] for item in listed.data["worktrees"]] == [worktree["id"]]
    assert listed.data["truncated"] is False
    assert denied.ok is False and denied.error is not None
    assert denied.error.code is ToolErrorCode.IRREVERSIBLE_BLOCKED
    assert discarded.data["ok"] is True and discarded.data["removed"] is True
    assert not Path(worktree["path"]).exists()
    assert again.data == {
        "ok": True,
        "worktree_id": worktree["id"],
        "removed": False,
        "reason": "not_found",
    }
    assert not Path(worktree["path"]).with_suffix(".json").exists()


def test_discard_refuses_running_task_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)
    started = asyncio.Event()
    gate = asyncio.Event()

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        started.set()
        await gate.wait()
        return LoopResult(reply="ok", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[dict[str, Any], Any]:
        result = await runtime.tools.ainvoke(
            "tools.delegate", {"task": "写代码", "background": True}, trace_id="t1"
        )
        data = cast(dict[str, Any], result.data)
        await started.wait()
        blocked = await runtime.tools.ainvoke(
            "tools.worktree.discard",
            {"worktree_id": cast(dict[str, Any], data["worktree"])["id"]},
            trace_id="t2",
            approved=True,
        )
        gate.set()
        await runtime.background_tasks.wait(cast(str, data["task_id"]))
        return cast(dict[str, Any], data["worktree"]), blocked

    worktree, blocked = asyncio.run(scenario())
    assert blocked.data["ok"] is False
    assert "占用" in cast(str, blocked.data["error"])
    assert Path(worktree["path"]).exists()


def test_discard_requires_force_for_dirty_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    coding = _coding_loop(runtime)

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        file_write().handler("dirty.txt", "unsaved\n")
        return LoopResult(reply="ok", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[dict[str, Any], Any, Any]:
        result = await runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        worktree = cast(dict[str, Any], cast(dict[str, Any], result.data)["worktree"])
        refused = await runtime.tools.ainvoke(
            "tools.worktree.discard",
            {"worktree_id": worktree["id"]},
            trace_id="t2",
            approved=True,
        )
        forced = await runtime.tools.ainvoke(
            "tools.worktree.discard",
            {"worktree_id": worktree["id"], "force": True},
            trace_id="t3",
            approved=True,
        )
        return worktree, refused, forced

    worktree, refused, forced = asyncio.run(scenario())
    assert refused.data["ok"] is False
    assert "force=true" in cast(str, refused.data["error"])
    assert forced.data["ok"] is True
    assert not Path(worktree["path"]).exists()


def test_worktree_tools_only_on_main_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo)
    main_ids = {tool.tool_id for tool in runtime.tools.active_tools()}
    assert {"tools.worktree.list", "tools.worktree.discard"} <= main_ids

    router = runtime.orchestrator._router  # noqa: SLF001
    profiles = [*router._agents.values(), router._fallback]  # noqa: SLF001
    for profile in profiles:
        sub_ids = {tool.tool_id for tool in profile.loop._tools.active_tools()}  # noqa: SLF001
        assert "tools.worktree.list" not in sub_ids
        assert "tools.worktree.discard" not in sub_ids


# ---- 权限口径 ----


def test_worktree_tools_classification_uses_tokens() -> None:
    engine = PolicyEngine()

    assert engine.classify("tools.worktree.list", "tools.worktree.list", []) is RiskLevel.READ
    assert (
        engine.classify("tools.worktree.discard", "tools.worktree.discard", [])
        is RiskLevel.HIGH_RISK
    )


def test_read_only_mode_denies_discard_but_allows_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, monkeypatch)
    runtime = _runtime(tmp_path, monkeypatch, cwd=repo, extra="permission:\n  mode: read-only\n")
    coding = _coding_loop(runtime)

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        return LoopResult(reply="ok", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> tuple[Any, Any]:
        result = await runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        worktree = cast(dict[str, Any], cast(dict[str, Any], result.data)["worktree"])
        listed = await runtime.tools.ainvoke("tools.worktree.list", {}, trace_id="t2")
        denied = await runtime.tools.ainvoke(
            "tools.worktree.discard",
            {"worktree_id": worktree["id"]},
            trace_id="t3",
            approved=True,
        )
        return listed, denied

    listed, denied = asyncio.run(scenario())
    assert listed.ok is True
    assert denied.ok is False and denied.error is not None
    assert denied.error.code is ToolErrorCode.GATE_DENIED


def test_auto_approve_allowlist_governs_worktree_coeffects() -> None:
    gate = PermissionModeGate(
        PermissionMode.AUTO_APPROVE,
        allowed_coeffects=frozenset({"agent:delegate", "worktree:read"}),
    )

    with pytest.raises(AccessControlError):
        gate.authorize("tools.worktree.discard", "tools.worktree.discard", ["worktree:write"])
    allowed = gate.authorize("tools.worktree.list", "tools.worktree.list", ["worktree:read"])
    assert allowed.allowed is True
