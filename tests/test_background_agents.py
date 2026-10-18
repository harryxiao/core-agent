"""后台子 Agent、完成通知与模型侧任务清单（change 0270）。

覆盖：

* **注册表**：`spawn` 立即返回；终态 done / failed / cancelled；运行中上限；
  强引用与 `wait`。
* **完成通知**：按会话记录、一次性 drain、每会话上界、渲染有界。
* **工具面**：`tools.delegate(background=true)` 不阻塞；`tools.tasks` 只读清单。
* **loop 接缝**：`notices_consult` 会话入参、异常降级、planner 独立块与逐字锚。
* **权限**：`tools.tasks` 字面量豁免判 read，`tasks` 词元不放宽。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager
from core.loop import DefaultLoop, LLMPlanner, LoopContext, LoopResult, current_session_id
from core.orchestration import OrchestrationError, OrchestrationErrorCode
from core.orchestration.background import (
    BackgroundAgentRegistry,
    BackgroundTaskInfo,
    render_notice_lines,
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


class _BlockingLoop:
    """子 Agent 桩：`arun` 阻塞到 gate 打开，记录收到的会话标识。"""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.sessions: list[str] = []

    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:
        self.sessions.append(session_id)
        await self.gate.wait()
        return LoopResult(reply=f"完成:{task}", trace_id="t-sub")


class _FailingLoop:
    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG002
        raise RuntimeError("内部细节不应外泄")


class _FailedResultLoop:
    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG002
        return LoopResult(reply="做不到", trace_id="t-sub", failed=True)


# ── 1. 注册表：spawn / 终态 / 通知 ──────────────────────────────────────────


def test_spawn_returns_immediately_and_completes() -> None:
    """`spawn` 立即返回 task_id；子 Agent 在后台跑，`wait` 后落 done。"""

    async def scenario() -> None:
        registry = BackgroundAgentRegistry()
        loop = _BlockingLoop()
        task_id = registry.spawn(loop, "写代码", agent_id="coding", session_id="s1")

        info = registry.get(task_id)
        assert info is not None
        assert info.status == "running"
        assert loop.gate.is_set() is False, "spawn 不得等待子 Agent"

        loop.gate.set()
        finished = await registry.wait(task_id)

        assert finished.status == "done"
        assert finished.reply == "完成:写代码"
        assert loop.sessions == ["s1"], "子 Agent 与前台委托一致地继承会话标识"

    asyncio.run(scenario())


def test_failed_subagent_does_not_leak_exception_text() -> None:
    """子 Agent 抛错 ⇒ failed；error 只留异常类型名（不把任意异常正文带回主对话）。"""

    async def scenario() -> None:
        registry = BackgroundAgentRegistry()
        task_id = registry.spawn(_FailingLoop(), "boom", agent_id="coding", session_id="s1")
        info = await registry.wait(task_id)

        assert info.status == "failed"
        assert "RuntimeError" in info.error
        assert "内部细节" not in info.error

    asyncio.run(scenario())


def test_failed_loop_result_marks_failed() -> None:
    """子 Agent 以 `failed=True` 收尾（未抛错）也落 failed。"""

    async def scenario() -> None:
        registry = BackgroundAgentRegistry()
        task_id = registry.spawn(_FailedResultLoop(), "做不到", agent_id="research", session_id="")
        info = await registry.wait(task_id)

        assert info.status == "failed"
        assert info.reply == "做不到"

    asyncio.run(scenario())


def test_cancel_marks_terminal_and_notifies() -> None:
    """取消 ⇒ cancelled 终态，且仍产生一条完成通知。"""

    async def scenario() -> None:
        registry = BackgroundAgentRegistry()
        loop = _BlockingLoop()
        task_id = registry.spawn(loop, "长任务", agent_id="coding", session_id="s1")
        await asyncio.sleep(0)  # 让任务真正开始
        registry.cancel(task_id)

        info = registry.get(task_id)
        assert info is not None
        assert info.status == "cancelled"
        notices = registry.drain_notices("s1")
        assert [n.task_id for n in notices] == [task_id]

    asyncio.run(scenario())


def test_running_tasks_are_bounded_and_finished_free_slots() -> None:
    """运行中上限 8：超限抛结构化错误；终态任务不占名额。"""

    async def scenario() -> None:
        registry = BackgroundAgentRegistry(max_running=2)
        loop = _BlockingLoop()
        first = registry.spawn(loop, "a", agent_id="coding", session_id="s1")
        registry.spawn(loop, "b", agent_id="coding", session_id="s1")

        with pytest.raises(OrchestrationError) as excinfo:
            registry.spawn(loop, "c", agent_id="coding", session_id="s1")
        assert excinfo.value.code is OrchestrationErrorCode.BACKGROUND_TASKS_FULL

        loop.gate.set()
        await registry.wait(first)
        assert registry.running_count() == 1
        registry.spawn(loop, "d", agent_id="coding", session_id="s1")
        registry.cancel_all()

    asyncio.run(scenario())


# ── 2. 完成通知：会话隔离 / 一次性 / 上界 ──────────────────────────────────


def test_notices_are_one_shot_and_session_scoped() -> None:
    """通知按会话一次性取走：drain 后清空，其他会话不受影响。"""

    async def scenario() -> None:
        registry = BackgroundAgentRegistry()
        loop = _BlockingLoop()
        loop.gate.set()
        first = registry.spawn(loop, "A", agent_id="coding", session_id="s1")
        second = registry.spawn(loop, "B", agent_id="research", session_id="s2")
        await registry.wait(first)
        await registry.wait(second)

        assert [n.task_id for n in registry.drain_notices("s1")] == [first]
        assert registry.drain_notices("s1") == []
        assert [n.task_id for n in registry.drain_notices("s2")] == [second]

    asyncio.run(scenario())


def test_notice_queue_is_bounded_per_session() -> None:
    """每会话待投递通知 ≤ 32：超出丢弃最旧，保留最近完成。"""

    async def scenario() -> None:
        registry = BackgroundAgentRegistry(max_running=1)
        loop = _BlockingLoop()
        loop.gate.set()
        ids: list[str] = []
        for index in range(registry.notice_cap + 3):
            task_id = registry.spawn(loop, f"t{index}", agent_id="coding", session_id="s1")
            await registry.wait(task_id)
            ids.append(task_id)

        notices = registry.drain_notices("s1")
        assert len(notices) == registry.notice_cap
        assert [n.task_id for n in notices] == ids[3:]

    asyncio.run(scenario())


def test_notice_line_is_bounded() -> None:
    """单行通知 ≤ 400 字符；单轮最多 10 行（渲染侧上界）。"""
    tasks = [
        BackgroundTaskInfo(
            task_id=f"bg-{i}",
            agent_id="coding",
            task="长" * 1000,
            status="done",
            started_at=0.0,
            finished_at=1.0,
            reply="果" * 1000,
        )
        for i in range(20)
    ]

    block = render_notice_lines(tasks)
    lines = block.splitlines()

    assert len(lines) == 10  # noqa: PLR2004 — 单轮渲染上界
    assert all(len(line) <= 400 for line in lines)  # noqa: PLR2004


# ── 3. loop 接缝：notices 字段 / planner 块 ────────────────────────────────


def _planner() -> LLMPlanner:
    return LLMPlanner(cast("Any", None))


def _ctx(**kwargs: Any) -> LoopContext:
    return LoopContext(messages=[{"role": "user", "content": "任务"}], **kwargs)


def test_loop_context_notices_defaults_empty() -> None:
    assert LoopContext().notices == ""


def test_notices_consult_passes_session_and_sets_field() -> None:
    seen: list[str] = []

    def consult(session_id: str) -> str:
        seen.append(session_id)
        return "- 后台任务完成：bg-1"

    loop = DefaultLoop(notices_consult=consult)
    ctx = _ctx(session_id="s7")

    loop._load_notices(ctx, "t1")  # noqa: SLF001 — 注入判据

    assert seen == ["s7"]
    assert ctx.notices == "- 后台任务完成：bg-1"


def test_notices_consult_degrades_on_error() -> None:
    def boom(_session_id: str) -> str:
        raise RuntimeError("boom")

    loop = DefaultLoop(notices_consult=boom)
    ctx = _ctx(session_id="s7")

    loop._load_notices(ctx, "t1")  # noqa: SLF001

    assert ctx.notices == ""


def test_planner_injects_notices_block() -> None:
    prompt = _planner()._system_prompt(  # noqa: SLF001 — 块装配判据
        _ctx(notices="- 后台任务完成：bg-1")
    )

    assert "后台任务通知：" in prompt
    assert "- 后台任务完成：bg-1" in prompt


def test_planner_omits_notices_when_empty_verbatim() -> None:
    planner = _planner()

    assert planner._system_prompt(_ctx()) == planner._system_prompt(  # noqa: SLF001
        _ctx(notices="")
    )
    assert "后台任务通知：" not in planner._system_prompt(_ctx())  # noqa: SLF001


def test_notices_block_order_after_failure_lessons() -> None:
    router = lambda _task: [{"skill_id": "s1", "version": "1"}]  # noqa: E731 — 桩路由
    planner = LLMPlanner(cast("Any", None), skill_router=cast("Any", router))
    prompt = planner._system_prompt(  # noqa: SLF001
        _ctx(notes="笔记", failure_lessons="- 失败：boom", notices="- 后台任务完成：bg-1")
    )

    assert prompt.index("既往失败教训：") < prompt.index("后台任务通知：")
    assert prompt.index("后台任务通知：") < prompt.index("可用技能：")


# ── 4. 工具面：后台委托 / 任务清单 / 权限 ─────────────────────────────────


def _runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_VALID_YAML, encoding="utf-8")
    return build_runtime(ConfigManager(yaml_path=config_path))


def test_delegate_background_returns_immediately_and_notifies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    coding = runtime.orchestrator._router._agents["coding"].loop  # noqa: SLF001

    async def scenario() -> None:
        gate = asyncio.Event()
        started = asyncio.Event()

        async def fake(task: str, *, session_id: str = "") -> LoopResult:
            started.set()
            await gate.wait()
            return LoopResult(reply=f"子任务完成:{task}", trace_id="t-sub")

        monkeypatch.setattr(coding, "arun", fake)
        token = current_session_id.set("s1")
        try:
            result = await runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码", "background": True}, trace_id="t1"
            )
            assert result.ok is True
            data = cast("dict[str, Any]", result.data)
            assert data["status"] == "running"
            task_id = data["task_id"]

            await started.wait()
            listed = await runtime.tools.ainvoke("tools.tasks", {"action": "list"}, trace_id="t1")
            assert any(item["task_id"] == task_id for item in listed.data["tasks"])

            gate.set()
            info = await runtime.background_tasks.wait(task_id)
            assert info.status == "done"
            notices = runtime.loop._notices_consult("s1")  # noqa: SLF001
            assert task_id in notices
            assert "子任务完成" in notices
        finally:
            current_session_id.reset(token)
            gate.set()

    asyncio.run(scenario())


def test_delegate_foreground_path_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """缺省（阻塞）路径仍返回 reply，不产生后台任务。"""
    runtime = _runtime(monkeypatch, tmp_path)
    coding = runtime.orchestrator._router._agents["coding"].loop  # noqa: SLF001

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        return LoopResult(reply="同步结果", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> None:
        result = await runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        assert result.data == {"ok": True, "reply": "同步结果"}
        assert runtime.background_tasks.list() == []

    asyncio.run(scenario())


def test_tasks_list_does_not_consume_notices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """清单查询是只读面：list 不清空待投递通知。"""
    runtime = _runtime(monkeypatch, tmp_path)
    coding = runtime.orchestrator._router._agents["coding"].loop  # noqa: SLF001

    async def fake(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        return LoopResult(reply="清单可见", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", fake)

    async def scenario() -> None:
        token = current_session_id.set("s1")
        try:
            result = await runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码", "background": True}, trace_id="t1"
            )
            task_id = cast("dict[str, Any]", result.data)["task_id"]
            await runtime.background_tasks.wait(task_id)

            listed = await runtime.tools.ainvoke("tools.tasks", {"action": "list"}, trace_id="t1")
            assert any(item["task_id"] == task_id for item in listed.data["tasks"])
            assert task_id in runtime.loop._notices_consult("s1")  # noqa: SLF001
        finally:
            current_session_id.reset(token)

    asyncio.run(scenario())


def test_delegate_background_over_cap_returns_structured_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """运行中已达上限 ⇒ 工具返回 ok=false（不排队、不起第 9 个任务）。"""
    runtime = _runtime(monkeypatch, tmp_path)
    coding = runtime.orchestrator._router._agents["coding"].loop  # noqa: SLF001
    blocker = asyncio.Event()

    async def forever(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        await blocker.wait()
        return LoopResult(reply="", trace_id="t-sub")

    monkeypatch.setattr(coding, "arun", forever)

    async def scenario() -> None:
        for _ in range(8):
            runtime.background_tasks.spawn(coding, "占位", agent_id="coding")
        try:
            result = await runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码", "background": True}, trace_id="t1"
            )
            assert result.ok is True  # 工具调用本身成功，业务结果是结构化失败
            assert result.data == {
                "ok": False,
                "error": "BACKGROUND_TASKS_FULL: 后台任务已达上限 8",
            }
            assert runtime.background_tasks.running_count() == 8  # noqa: PLR2004
        finally:
            runtime.background_tasks.cancel_all()
            blocker.set()

    asyncio.run(scenario())


def test_tasks_tool_status_unknown_id_found_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _runtime(monkeypatch, tmp_path)

    async def scenario() -> None:
        result = await runtime.tools.ainvoke(
            "tools.tasks", {"action": "status", "task_id": "nope"}, trace_id="t1"
        )
        assert result.ok is True
        assert result.data == {"task_id": "nope", "found": False}

    asyncio.run(scenario())


def test_tasks_tool_classified_read_without_token_relaxation() -> None:
    engine = PolicyEngine()

    assert engine.classify("tools.tasks", "tools.tasks", ["task:read"]) is RiskLevel.READ
    assert engine.classify("tools.tasks_purge", "tools.tasks_purge", ["task:read"]) is not (
        RiskLevel.READ
    )


def test_runtime_wires_background_capability_only_on_main_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    ids = {tool.tool_id for tool in runtime.tools.active_tools()}
    assert "tools.tasks" in ids
    assert runtime.loop._notices_consult is not None  # noqa: SLF001

    router = runtime.orchestrator._router  # noqa: SLF001
    profiles = list(router._agents.values())  # noqa: SLF001
    profiles.append(router._fallback)  # noqa: SLF001
    for profile in profiles:
        assert profile.loop is not runtime.loop
        sub_ids = {tool.tool_id for tool in profile.loop._tools.active_tools()}  # noqa: SLF001
        assert "tools.tasks" not in sub_ids
        assert "tools.delegate" not in sub_ids
        assert profile.loop._notices_consult is None  # noqa: SLF001
