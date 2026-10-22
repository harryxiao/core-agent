"""遗忘的检索隔离（change 0301 / 规格「记忆遗忘（forgetting）」）。

旧实现：``forget()`` 只把低分条目迁 L4（``store.py:786``），``read()`` 不过滤层
（L4 仅经权重降权），``failure_lessons()`` 亦层无关 ⇒ 被「遗忘」的内容仍从**两个注入面**
进入提示词。本文件钉住：遗忘 = 打 ``forgotten`` 标签 + 退出注入面 + 审计可追溯 + 可回滚；
「归档 ≠ 遗忘」（压实/闸门产生的 L4 仍可召回）。
"""

from __future__ import annotations

import time

from core.memory import FileBackend, MemoryEntry, MemoryStore
from core.plugin_registry import EffectTracker

_OLD_TS = time.time() - 10 * 365 * 86400  # 十年前：衰减评分必低于遗忘阈值


def _old_entry(
    entry_id: str,
    *,
    content: str = "旧事实",
    tags: list[str] | None = None,
    session_id: str = "s1",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=list(tags or []),
        source="loop",
        trace_id="t",
        ts=_OLD_TS,
        session_id=session_id,
    )


def _store(tracker: EffectTracker | None = None) -> MemoryStore:
    return MemoryStore(backend=FileBackend(), effect_tracker=tracker or EffectTracker())


def test_forgotten_entry_not_recalled_by_default() -> None:
    """遗忘归档 ⇒ 缺省 ``read()`` 不再返回（旧实现 L4 仍可召回）。"""
    store = _store()
    store.write("L2", _old_entry("e0", content="被遗忘的旧事实"))
    assert store.forget() == ["e0"]

    assert store.read("旧事实") == []


def test_forgotten_entry_excluded_before_budget() -> None:
    """排除发生在排名与预算**之前**：遗忘条目不吃预算、不挤掉可召回条目。"""
    store = _store()
    gone = _old_entry("gone", content="alpha " * 400)  # 唯一命中查询、且超预算
    gone.ts = time.time()  # 时间新 ⇒ 排名确定在 keep 之前
    store.write("L2", gone)
    assert store.forget(threshold=10.0) == ["gone"]  # 强制遗忘（阈值高于评分上界）
    keep = _old_entry("keep", content="无关内容")  # 不命中查询，但仍在候选集
    keep.ts = time.time()
    store.write("L2", keep)

    assert [e.id for e in store.read("alpha", budget=100)] == ["keep"]


def test_include_forgotten_returns_them() -> None:
    """``include_forgotten=True`` 是显式回溯面：仍可见（层级 L4、标签仍在）。"""
    store = _store()
    store.write("L2", _old_entry("e0", content="被遗忘的旧事实"))
    store.forget()

    recalled = store.read("旧事实", include_forgotten=True)
    assert [e.id for e in recalled] == ["e0"]
    assert recalled[0].layer == "L4"
    assert "forgotten" in recalled[0].tags


def test_audit_still_visible_after_forget() -> None:
    """墓碑语义：``audit()`` 仍可查得（保留 id/时间/内容供追溯）。"""
    store = _store()
    store.write("L2", _old_entry("e0"))
    store.forget()

    audited = {e.id: e for e in store.audit()}
    assert audited["e0"].layer == "L4"
    assert "forgotten" in audited["e0"].tags


def test_failure_lessons_excludes_forgotten() -> None:
    """第二个注入面：失败教训读面同样不返回已遗忘条目。"""
    store = _store()
    store.write("L2", _old_entry("f0", content="失败教训", tags=["loop", "failure"]))
    assert store.forget() == ["f0"]

    assert store.failure_lessons("s1") == []
    assert [e.id for e in store.audit()] == ["f0"]  # 审计仍可见


def test_rollback_forget_restores_recall() -> None:
    """按遗忘 trace 回滚 ⇒ 迁回 L2、移除 ``forgotten`` 标签、重新可召回。"""
    tracker = EffectTracker()
    store = _store(tracker)
    store.write("L2", _old_entry("e0", content="被遗忘的旧事实"))
    store.forget()

    tracker.rollback("forgetting.e0")

    recalled = store.audit()
    assert [(e.id, e.layer) for e in recalled] == [("e0", "L2")]
    assert "forgotten" not in recalled[0].tags
    assert [e.id for e in store.read("旧事实")] == ["e0"]


def test_non_forget_archived_entry_still_recalled() -> None:
    """「归档 ≠ 遗忘」：压实/闸门产生的 L4 条目（无标签）仍可召回。"""
    store = _store()
    store.write("L2", _old_entry("e0", content="压实归档的旧事实"))
    store.migrate("e0", "L2", "L4", trace_id="compaction.t")

    recalled = store.read("压实归档")
    assert [e.id for e in recalled] == ["e0"]
    assert "forgotten" not in recalled[0].tags
