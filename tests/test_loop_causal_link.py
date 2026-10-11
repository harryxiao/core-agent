"""情景链（时序相邻标注）（change 0202 / ADR-0192 / 账本 E139）。

三面：
  * **标注**：失败条目 `tags` 增 `after:<前序 trace>`（**时序相邻**，非因果）——缺省**关** ⇒ 逐字不变
  * **不遮蔽**：新标签 SHALL NOT 改变该条目在「压实材料排除面」与「相关事实注入面」上的去留
  * **只读链**：`MemoryStore.session_chain` —— 按 ts 序、跨会话不混、**零效应**
"""

from __future__ import annotations

from core.context import DynamicAssembler
from core.loop import DefaultLoop
from core.memory import MemoryStore
from core.plugin_registry import EffectTracker

# 事实面用例构造的**轮数** —— 每轮一条失败摘要条目，故含「失败：」的事实恰为本值。
_ROUNDS = 2


def _fail(loop: DefaultLoop, trace_id: str, session_id: str = "s1") -> None:
    loop.remember(
        trace_id,
        [{"round": 1, "ok": False, "error": "boom"}],
        session_id=session_id,
        failed=True,
    )


def _tags(store: MemoryStore, entry_id: str) -> list[str]:
    entries = {str(entry.id): entry for entry in store.audit()}
    return list(entries[entry_id].tags)


# ---- 标注面 ----


def test_disabled_leaves_failure_tags_verbatim() -> None:
    """**逐字锚**：缺省关 ⇒ 失败条目 `tags` 恰为既有取值，无任何 `after:` 值。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store)
    _fail(loop, "t1")
    _fail(loop, "t2")
    assert _tags(store, "loop.failure.t1") == ["loop", "failure"]
    assert _tags(store, "loop.failure.t2") == ["loop", "failure"]


def test_enabled_marks_temporal_adjacency() -> None:
    """开 ⇒ 第二轮失败标注**上一已记忆轮**；首轮无前序 ⇒ 不带标注。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store, causal_links=True)
    _fail(loop, "t1")
    _fail(loop, "t2")
    assert _tags(store, "loop.failure.t1") == ["loop", "failure"]
    assert _tags(store, "loop.failure.t2") == ["loop", "failure", "after:t1"]


def test_chain_does_not_cross_sessions() -> None:
    """前序**按会话**维护 ⇒ 另一会话的轮不成为本会话的前序。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store, causal_links=True)
    _fail(loop, "a1", "s1")
    _fail(loop, "b1", "s2")
    _fail(loop, "a2", "s1")
    assert _tags(store, "loop.failure.a2") == ["loop", "failure", "after:a1"]
    assert _tags(store, "loop.failure.b1") == ["loop", "failure"]


# ---- 不遮蔽面 ----


def test_marked_failure_still_excluded_from_compaction_material() -> None:
    """`failure` 标签仍在 ⇒ 仍被压实材料排除（`_episodic_groups` 即**唯一材料源**）。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store, causal_links=True)
    _fail(loop, "t1")
    _fail(loop, "t2")
    # 材料源的唯一入口，直测最精确（私有面：ruff SLF001 + pyright reportPrivateUsage 双抑制）
    material = store._episodic_groups("s1")  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    ids = {str(entry.id) for entries in material.values() for entry in entries}
    assert "loop.failure.t2" not in ids
    assert "loop.t2" in ids  # 轨迹条目**不受**影响


def test_marked_failure_still_reaches_the_fact_face() -> None:
    """事实面按 `steps` 标签排除 ⇒ 无 `steps` 的失败条目**仍进**「相关事实」。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store, causal_links=True)
    loop.remember(
        "t1",
        [{"round": 1, "ok": False, "error": "boom"}],
        session_id="s1",
        steps=["tools.echo（text: x） → 错误：bad"],
        failed=True,
    )
    loop.remember(
        "t2",
        [{"round": 1, "ok": False, "error": "boom"}],
        session_id="s1",
        steps=["tools.echo（text: y） → 错误：bad"],
        failed=True,
    )
    assembler = DynamicAssembler(memory=store, exclude_fact_tags=frozenset({"steps"}))
    contents = [fact["content"] for fact in assembler.build("t", "reason", budget=4096).facts]
    assert sum("失败：" in content for content in contents) == _ROUNDS, "两条失败条目仍须在事实面"
    # 对照：**纯步序**条目（内容恰为步序）仍被 `steps` 标签挡在事实面外。
    # 注意失败摘要**自身内嵌**步序文本 ⇒ 只能按**整条相等**判定，不能按子串。
    assert "tools.echo（text: y） → 错误：bad" not in contents, "纯步序条目仍须被挡（对照）"


# ---- 只读链 ----


def test_session_chain_ordered_isolated_and_zero_effect() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)
    loop = DefaultLoop(memory=store, causal_links=True)
    _fail(loop, "a1", "s1")
    _fail(loop, "b1", "s2")
    _fail(loop, "a2", "s1")

    before_reuse = {str(entry.id): entry.reuse_count for entry in store.audit()}
    before_effects = {tid: len(tracker.audit(tid)) for tid in ("a1", "b1", "a2")}
    before_ids = set(before_reuse)

    chain = store.session_chain("s1")

    assert [node.trace_id for node in chain] == ["a1", "a1", "a2", "a2"], "只含 s1 且按 ts 序"
    assert [node.ts for node in chain] == sorted(node.ts for node in chain)
    assert [node.failed for node in chain] == [False, True, False, True], "轨迹环 / 失败环交替"
    assert chain[-1].after == "a1"  # 末环 = 第二轮失败条目

    after = {str(entry.id): entry.reuse_count for entry in store.audit()}
    assert set(after) == before_ids, "只读链不得新增条目"
    assert after == before_reuse, "只读链不得强化复用计数"
    assert {tid: len(tracker.audit(tid)) for tid in ("a1", "b1", "a2")} == before_effects


def test_session_chain_without_filter_returns_all_and_empty_is_empty() -> None:
    store = MemoryStore()
    loop = DefaultLoop(memory=store, causal_links=True)
    _fail(loop, "a1", "s1")
    _fail(loop, "b1", "s2")

    assert sorted(node.trace_id for node in store.session_chain()) == ["a1", "a1", "b1", "b1"]
    assert store.session_chain("nope") == []
