"""后台子 Agent 跨重启登记与重入队（change 0279 / ADR-0269）。

覆盖：

* **落盘**：终态即时落盘、0600、损坏容忍、条目有界、任务正文/错误脱敏。
* **重启映射**：`running → interrupted`（终态、不占运行名额、不重放通知、不可取消）。
* **重入队**：`tools.task_retry` 只接受 interrupted/failed/cancelled；新 `task_id`；
  运行中上限结构化失败；runtime 只挂主工具面且判 `HIGH_RISK`。
"""

from __future__ import annotations

import asyncio
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.loop import LoopResult
from core.orchestration import AgentProfile
from core.orchestration.background import (
    BackgroundAgentRegistry,
    task_retry_tool,
)
from core.permission import PolicyEngine, RiskLevel
from core.runtime import build_runtime

_VALID_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
"""

_CANARY = "sk-abcdefghijklmnop"
_FILE_MODE = 0o600


class _OkLoop:
    def __init__(self) -> None:
        self.tasks: list[str] = []
        self.sessions: list[str] = []

    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:
        self.tasks.append(task)
        self.sessions.append(session_id)
        return LoopResult(reply=f"完成:{task}", trace_id="t-sub")


class _FailingLoop:
    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG002
        raise RuntimeError("boom")


class _BlockingLoop:
    def __init__(self) -> None:
        self.gate = asyncio.Event()

    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG002
        await self.gate.wait()
        return LoopResult(reply="完成", trace_id="t-sub")


def _record(task_id: str, started_at: float, *, status: str = "done") -> dict[str, Any]:
    return {
        "task_id": task_id,
        "agent_id": "coding",
        "task": f"任务 {task_id}",
        "status": status,
        "started_at": started_at,
        "finished_at": started_at + 1,
        "session_id": "s1",
        "error": "",
    }


def _write_state(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"version": 1, "tasks": tasks}), encoding="utf-8")


# ── 1. 落盘 ────────────────────────────────────────────────────────────────


def test_terminal_status_restored_by_new_registry(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"

    async def scenario() -> str:
        registry = BackgroundAgentRegistry(state_path=path)
        task_id = registry.spawn(_OkLoop(), "写代码", agent_id="coding", session_id="s1")
        await registry.wait(task_id)
        return task_id

    task_id = asyncio.run(scenario())
    assert stat.S_IMODE(path.stat().st_mode) == _FILE_MODE

    restored = BackgroundAgentRegistry(state_path=path)
    info = restored.get(task_id)
    assert info is not None
    assert info.status == "done"
    assert info.agent_id == "coding"
    assert info.task == "写代码"
    # 回复正文不落盘：重启后只保留状态
    assert info.reply == ""
    # 对模型暴露的快照不含会话标识
    assert "session_id" not in info.info()


def test_without_state_path_writes_nothing(tmp_path: Path) -> None:
    async def scenario() -> None:
        registry = BackgroundAgentRegistry()
        task_id = registry.spawn(_OkLoop(), "写代码", agent_id="coding")
        await registry.wait(task_id)

    asyncio.run(scenario())
    assert list(tmp_path.glob("*.json")) == []


def test_corrupt_file_warns_once_and_starts_empty(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.warns(UserWarning, match="后台任务登记文件损坏"):
        registry = BackgroundAgentRegistry(state_path=path)
    assert registry.list() == []


def test_entries_bounded_to_newest(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"
    _write_state(path, [_record(f"bg-{i}", float(i)) for i in range(5)])

    registry = BackgroundAgentRegistry(state_path=path, max_records=3)
    assert [info.task_id for info in registry.list()] == ["bg-2", "bg-3", "bg-4"]


def test_secret_redacted_before_persist(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"

    async def scenario() -> None:
        registry = BackgroundAgentRegistry(state_path=path)
        loop = _BlockingLoop()
        registry.spawn(loop, f"调 API {_CANARY} 后报告", agent_id="coding", session_id="s1")
        loop.gate.set()
        for info in registry.list():
            await registry.wait(info.task_id)

    asyncio.run(scenario())
    raw = path.read_text(encoding="utf-8")
    assert _CANARY not in raw
    assert "<redacted>" in raw


# ── 2. 重启映射 ────────────────────────────────────────────────────────────


def test_running_task_becomes_interrupted_on_restart(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"
    # 重启 = 新进程：用已退出子进程的 pid 模拟死 owner（同进程双实例属“存活 owner”，
    # 见 tests/test_background_ownership.py）。
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    _write_state(
        path,
        [
            {
                **_record("bg-restart", 1.0, status="running"),
                "finished_at": None,
                "owner_pid": proc.pid,
                "owner_start": "",
            }
        ],
    )

    restored = BackgroundAgentRegistry(state_path=path)
    info = restored.get("bg-restart")
    assert info is not None
    assert info.status == "interrupted"
    assert info.finished_at is None
    assert "进程重启" in info.error
    assert restored.running_count() == 0
    assert restored.cancel("bg-restart") is False, "被中断任务没有在途 asyncio.Task"
    assert restored.drain_notices("s1") == [], "重启不重放完成通知"


# ── 3. 重入队 ──────────────────────────────────────────────────────────────


def _tool(registry: BackgroundAgentRegistry, loop: Any) -> Any:
    return task_retry_tool(
        registry=registry,
        match=lambda task: AgentProfile("coding", ["写代码"], loop=loop),
    )


def test_retry_failed_task_spawns_new_task(tmp_path: Path) -> None:
    async def scenario() -> None:
        registry = BackgroundAgentRegistry(state_path=tmp_path / "background-tasks.json")
        failed_id = registry.spawn(_FailingLoop(), "写代码", agent_id="coding", session_id="s1")
        await registry.wait(failed_id)
        assert registry.get(failed_id).status == "failed"  # type: ignore[union-attr]

        ok = _OkLoop()
        result = await _tool(registry, ok).handler(task_id=failed_id)
        assert result["ok"] is True
        assert result["status"] == "running"
        assert result["task_id"] != failed_id
        assert result["retried"] == failed_id

        await registry.wait(result["task_id"])
        assert ok.tasks == ["写代码"]
        assert ok.sessions == ["s1"], "重入队恢复原会话归属"
        assert registry.get(failed_id).status == "failed", "原任务终态保持不变"  # type: ignore[union-attr]

    asyncio.run(scenario())


def test_retry_rejects_running_done_and_unknown(tmp_path: Path) -> None:
    async def scenario() -> None:
        registry = BackgroundAgentRegistry(state_path=tmp_path / "background-tasks.json")
        blocking = _BlockingLoop()
        running_id = registry.spawn(blocking, "长任务", agent_id="coding")
        done_id = registry.spawn(_OkLoop(), "已完成", agent_id="coding")
        await registry.wait(done_id)
        tool = _tool(registry, _OkLoop())

        running = await tool.handler(task_id=running_id)
        assert running["ok"] is False and "仍在运行" in running["error"]
        done = await tool.handler(task_id=done_id)
        assert done["ok"] is False and "已完成" in done["error"]
        unknown = await tool.handler(task_id="bg-nope")
        assert unknown["ok"] is False and "未登记" in unknown["error"]

        blocking.gate.set()
        await registry.wait(running_id)

    asyncio.run(scenario())


def test_retry_respects_running_capacity(tmp_path: Path) -> None:
    async def scenario() -> None:
        registry = BackgroundAgentRegistry(
            state_path=tmp_path / "background-tasks.json", max_running=1
        )
        failed_id = registry.spawn(_FailingLoop(), "写代码", agent_id="coding")
        await registry.wait(failed_id)
        blocking = _BlockingLoop()
        running_id = registry.spawn(blocking, "占位", agent_id="coding")

        result = await _tool(registry, _OkLoop()).handler(task_id=failed_id)
        assert result["ok"] is False
        assert "上限" in result["error"]

        blocking.gate.set()
        await registry.wait(running_id)

    asyncio.run(scenario())


def test_retry_uses_redacted_text_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"
    _write_state(
        path,
        [
            {
                "task_id": "bg-old",
                "agent_id": "coding",
                "task": f"调 API {_CANARY} 后报告",
                "status": "interrupted",
                "started_at": 1.0,
                "finished_at": None,
                "session_id": "s1",
                "error": "进程重启导致中断",
            }
        ],
    )
    registry = BackgroundAgentRegistry(state_path=path)
    seen: list[str] = []
    tool = task_retry_tool(
        registry=registry,
        match=lambda task: (seen.append(task), AgentProfile("coding", ["x"], loop=_OkLoop()))[1],
    )

    async def scenario() -> None:
        result = await tool.handler(task_id="bg-old")
        assert result["ok"] is True
        assert seen == ["调 API <redacted> 后报告"]
        await registry.wait(result["task_id"])

    asyncio.run(scenario())


# ── 4. runtime 接线与权限 ─────────────────────────────────────────────────


def _runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_VALID_YAML, encoding="utf-8")
    return build_runtime(ConfigManager(yaml_path=config_path))


def test_runtime_registers_retry_only_on_main_surface(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    assert "tools.task_retry" in {tool.tool_id for tool in runtime.tools.active_tools()}

    router = runtime.orchestrator._router  # noqa: SLF001
    profiles = [*router._agents.values(), router._fallback]  # noqa: SLF001
    for profile in profiles:
        sub_ids = {tool.tool_id for tool in profile.loop._tools.active_tools()}  # noqa: SLF001
        assert "tools.task_retry" not in sub_ids


def test_task_retry_classified_high_risk() -> None:
    engine = PolicyEngine()
    assert engine.classify("tools.task_retry", "tools.task_retry", ["task:write"]) is (
        RiskLevel.HIGH_RISK
    )
