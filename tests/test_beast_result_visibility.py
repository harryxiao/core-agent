"""神兽任务**结果可见性**（change 0113 / phase-28 E46）。

背景（一手复核）：`beast/manager.py:71` `await handoff` **已拿到** `LoopResult` → `:74` 存入
`session.last_result`，而该属性 repo-wide **零读者**；`entry.py:1750` `_summon` 只打印状态。
本 change 补**只读查询面**（`BeastSession.result_summary()`）+ `summon` CLI 呈现结果正文。

硬边界（规格）：结果可见性走**查询面**，**不落 L2** —— 账本原写「经 `session.remember()` 落 L2」
**自败**（`runtime.py:564` 主 loop `exclude_source_prefixes=("beast.",)` + `beast-mode/spec.md:89`
记忆分区封存 ⇒ 落进去主 Agent 永远检索不到）。本文件含守护用例钉住「查询**零**记忆写入」。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core.beast import BeastActivator, BeastManager, BeastRegistry, BeastSession
from core.entry import main
from core.loop import LoopResult
from core.memory import MemoryEntry


class _SpyMemory:
    def __init__(self) -> None:
        self.written: list[MemoryEntry] = []

    def write(self, layer: str, entry: MemoryEntry) -> str | None:
        self.written.append(entry)
        return entry.id

    def read(self, query: str, budget: int = 4096, **kw: Any) -> list[MemoryEntry]:
        return []


class _Router:
    """duck-typed 路由器：`handoff` 返回受控 `LoopResult`（不出网、不跑真 loop）。"""

    def __init__(self, *, reply: str = "蓝图已就绪", failed: bool = False) -> None:
        self.reply = reply
        self.failed = failed
        self.handed: list[str] = []

    def register(self, profile: Any) -> None:  # noqa: ARG002 — 只用其副作用
        return None

    async def handoff(self, agent_id: str, handoff: Any) -> LoopResult:  # noqa: ARG002
        self.handed.append(agent_id)
        return LoopResult(reply=self.reply, trace_id="t1", failed=self.failed)


def _qinglong() -> Any:
    beast = BeastRegistry().resolve("beast.qinglong")
    assert beast is not None
    return beast


# ---- 查询面：结果取自会话持有的 last_result ----


def test_result_summary_before_run_reports_no_result() -> None:
    """未执行过 ⇒ 明确「无结果」，不编造正文。"""
    session = BeastSession(_qinglong())
    summary = session.result_summary()
    assert summary["agent_id"] == "beast.qinglong"
    assert summary["has_result"] is False
    assert summary["reply"] is None
    assert summary["failed"] is None


def test_result_summary_exposes_reply_and_failure() -> None:
    """执行过 ⇒ 暴露正文与成败（数据源 = `last_result`）。"""
    session = BeastSession(_qinglong())
    session.last_result = LoopResult(reply="分布式蓝图：三阶段", trace_id="t1", failed=False)
    summary = session.result_summary()
    assert summary["has_result"] is True
    assert summary["reply"] == "分布式蓝图：三阶段"
    assert summary["failed"] is False


def test_result_summary_reflects_failed_run() -> None:
    session = BeastSession(_qinglong())
    session.last_result = LoopResult(reply="", trace_id="t1", failed=True)
    assert session.result_summary()["failed"] is True


# ---- 守护：查询零记忆写入（不落 L2、不失封存） ----


def test_query_writes_nothing_to_memory() -> None:
    """结果查询**不落 L2** —— 无第二写路径，`source=beast.*` 封存语义不被结果面触碰。"""
    memory = _SpyMemory()
    session = BeastSession(_qinglong(), memory=memory)
    session.last_result = LoopResult(reply="不该进 L2 的正文", trace_id="t1")
    session.result_summary()
    assert memory.written == []


def test_summon_does_not_write_result_to_l2() -> None:
    """召唤全流程同样不因结果可见性而写 L2（写入侧仍是 `_beast_loop` 的 source 注入，未改）。"""
    memory = _SpyMemory()
    manager = BeastManager(router=_Router(), memory=memory)
    session = asyncio.run(manager.summon("beast.qinglong", "设计分布式架构"))
    assert session.result_summary()["reply"] == "蓝图已就绪"
    assert memory.written == []


# ---- CLI 面：summon 呈现结果 ----


class _FakeRuntime:
    def __init__(self, activator: BeastActivator) -> None:
        self.beast_activator = activator


def _summon_argv(*extra: str) -> list[str]:
    return ["summon", "beast.qinglong", *extra]


def test_cli_summon_prints_result_reply(
    monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """召唤后 stdout 含结果正文（结果对象已到手，接出来即可）。"""
    manager = BeastManager(router=_Router(reply="蓝图：先分层再收敛"))
    monkeypatch.setattr(
        "core.entry.build_runtime", lambda *a, **kw: _FakeRuntime(BeastActivator(manager))
    )
    assert main(_summon_argv("设计", "架构")) == 0
    out = capsys.readouterr().out
    assert "蓝图：先分层再收敛" in out
    assert "beast.qinglong" in out


def test_cli_summon_without_router_does_not_fabricate_reply(
    monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """无 router（无交接 ⇒ 无结果）⇒ 只报状态，**不**编造结果正文。"""
    manager = BeastManager()  # 无 router ⇒ summon 不产出 LoopResult
    monkeypatch.setattr(
        "core.entry.build_runtime", lambda *a, **kw: _FakeRuntime(BeastActivator(manager))
    )
    assert main(_summon_argv("设计", "架构")) == 0
    out = capsys.readouterr().out
    assert "beast.qinglong" in out
    assert "结果" not in out  # 无结果行
