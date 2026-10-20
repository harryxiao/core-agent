"""0296 · 压实的协作式截止与单飞。

事故：轮内压实 `wait_for` 只放弃等待，工作线程仍逐条打分（最多 20 次）并逐会话摘要，
端点挂起时可把一轮拖到 140s+；CLI `memory maintain` 完全没有上限。

本文件钉住 `MemoryStore.compact(deadline=...)` 的协作式边界与 single-flight：
截止前零调用、调用之间停止、摘要返回后越界不提交、并发触发非阻塞跳过。
"""

from __future__ import annotations

import threading
import time
from typing import Any, cast

from core.judgment import Compactor
from core.memory import MemoryEntry, MemoryStore


def _entry(entry_id: str = "e1", *, session_id: str = "s1") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=f"事件 {entry_id}",
        tags=["loop"],
        source="loop",
        trace_id=f"t.{entry_id}",
        session_id=session_id,
        kind="episodic",
    )


class _ScoreResult:
    def __init__(self, value: float = 0.9) -> None:
        self.answers = {"score": {"score": value}}


class _Scorer:
    """memory 的 `Compactor` 协议替身：每次打分推进注入时钟。"""

    def __init__(self, clock: list[float], step: float) -> None:
        self._clock = clock
        self._step = step
        self.calls: list[str] = []

    def score(
        self,
        state: dict[str, Any],
        entries: list[dict[str, Any]],
        threshold: float | None = None,
    ) -> _ScoreResult:
        self.calls.append(str(entries[0]["id"]))
        self._clock[0] += self._step
        return _ScoreResult()


class _Summarizer:
    def __init__(
        self,
        *,
        advance: list[float] | None = None,
        to: float = 0.0,
        entered: threading.Event | None = None,
        release: threading.Event | None = None,
    ) -> None:
        self.calls = 0
        self._advance = advance
        self._to = to
        self._entered = entered
        self._release = release
        self.started = threading.Event()

    def __call__(self, material: list[MemoryEntry]) -> str:
        self.calls += 1
        self.started.set()
        if self._entered is not None:
            self._entered.set()
        if self._release is not None:
            self._release.wait(timeout=2.0)
        if self._advance is not None:
            self._advance[0] = self._to
        return "会话摘要"


def test_expired_deadline_makes_zero_model_calls() -> None:
    """截止早于当前时钟 ⇒ 打分与摘要都不调用、不写摘要。"""
    now = [10.0]
    scorer = _Scorer(now, step=0.0)
    summarizer = _Summarizer()
    store = MemoryStore(
        clock=lambda: now[0], compactor=cast(Compactor, scorer), summarizer=summarizer
    )
    store.write("L2", _entry())

    store.compact(session_id="s1", deadline=9.0)

    assert scorer.calls == []
    assert summarizer.calls == 0
    assert store.summary_for("s1") is None


def test_deadline_stops_between_scoring_calls() -> None:
    """截止落在第 1、2 次打分之间 ⇒ 只执行第 1 次，后续摘要也不发起。"""
    now = [0.0]
    scorer = _Scorer(now, step=6.0)
    summarizer = _Summarizer()
    store = MemoryStore(
        clock=lambda: now[0], compactor=cast(Compactor, scorer), summarizer=summarizer
    )
    for index in range(3):
        store.write("L2", _entry(f"e{index}"))

    store.compact(session_id="s1", deadline=6.0)

    assert len(scorer.calls) == 1
    assert summarizer.calls == 0
    assert store.summary_for("s1") is None


def test_summary_returned_after_deadline_is_not_committed() -> None:
    """摘要调用返回时已越过截止 ⇒ 不提交摘要、不迁移原条目。"""
    now = [0.0]
    summarizer = _Summarizer(advance=now, to=100.0)
    store = MemoryStore(clock=lambda: now[0], summarizer=summarizer)
    store.write("L2", _entry())

    store.compact(session_id="s1", deadline=50.0)

    assert summarizer.calls == 1
    assert store.summary_for("s1") is None
    entry = next(entry for entry in store.audit() if entry.id == "e1")
    assert entry.layer == "L2", "截止后不得迁移材料条目"


def test_concurrent_compaction_is_skipped_without_calls() -> None:
    """已有压实执行时，第二次调用立即返回 None，不产生额外模型调用。"""
    now = [0.0]
    release = threading.Event()
    entered = threading.Event()
    summarizer = _Summarizer(entered=entered, release=release)
    store = MemoryStore(clock=lambda: now[0], summarizer=summarizer)
    store.write("L2", _entry())

    worker = threading.Thread(target=lambda: store.compact(session_id="s1"))
    worker.start()
    assert entered.wait(timeout=2.0), "第一次压实应已进入摘要调用"

    started = time.monotonic()
    assert store.compact(session_id="s1") is None
    elapsed = time.monotonic() - started

    release.set()
    worker.join(timeout=2.0)

    assert elapsed < 0.2, f"并发压实必须非阻塞跳过（实测 {elapsed:.3f}s）"  # noqa: PLR2004
    assert summarizer.calls == 1, "第二次不得发起新的摘要调用"
    assert store.summary_for("s1") is not None, "第一次压实应正常完成"


def test_no_deadline_keeps_existing_behavior() -> None:
    """不传 deadline 且无并发 ⇒ 摘要正常落库（既有行为逐字不变）。"""
    summarizer = _Summarizer()
    store = MemoryStore(summarizer=summarizer)
    store.write("L2", _entry())

    store.compact(session_id="s1")

    summary = store.summary_for("s1")
    assert summary is not None
    assert summary.content == "会话摘要"
    assert summarizer.calls == 1
