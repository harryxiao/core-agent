"""记忆条目治理信封与关键事实版本链（version chain）单测。

对应规格：doc/openspec/specs/memory/spec.md「记忆条目的治理信封」「结构化实体抽取（关键事实）」
「关键事实的跨压实合并」。
change 0303 / ADR-0293 / 台账 E239（memory-sdd P1-1 子集 + P1-2）。
"""

from __future__ import annotations

import hashlib
import json

from core.memory import REDACTED, FileBackend, KeyFact, MemoryEntry, MemoryStore, Relation
from core.plugin_registry import EffectTracker


def _episodic(entry_id: str, session_id: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content="事件",
        tags=["loop"],
        source="loop",
        session_id=session_id,
        kind="episodic",
        trace_id="t",
    )


def _store(
    holder: dict[str, list[KeyFact]], *, tracker: EffectTracker | None = None
) -> MemoryStore:
    return MemoryStore(
        effect_tracker=tracker,
        summarizer=lambda entries: "摘要：事实",
        key_fact_extractor=lambda entries: list(holder["facts"]),
    )


def _facts(store: MemoryStore) -> list[MemoryEntry]:
    return [entry for entry in store.audit() if "key_fact" in entry.tags]


def _digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def test_legacy_rows_load_with_envelope_defaults(tmp_path) -> None:
    """变更前写入的 JSONL 行（无治理字段）⇒ 缺键取默认值，检索可见性与旧行为一致。"""
    legacy = {
        "id": "legacy-1",
        "layer": "L2",
        "content": "旧格式条目",
        "tags": [],
        "source": "loop",
        "trace_id": "t",
        "reuse_count": 0,
        "ts": 1.0,
        "session_id": "",
        "importance": 0.0,
        "kind": "episodic",
    }
    path = tmp_path / "memory.jsonl"
    path.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")

    store = MemoryStore(backend=FileBackend(path))

    entry = next(item for item in store.read("旧格式") if item.id == "legacy-1")
    assert entry.status == "active"
    assert entry.version == 1
    assert entry.parent_id == "" and entry.superseded_by == ""
    assert entry.content_hash == ""


def test_first_version_carries_envelope_defaults() -> None:
    """首版：status=active、version=1、无父版本、content_hash 与正文同源。"""
    store = _store({"facts": [KeyFact(entity="部署环境", value="生产集群 A")]})
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    entry = _facts(store)[0]
    assert entry.id == "keyfact.部署环境"
    assert entry.status == "active"
    assert entry.version == 1
    assert entry.parent_id == ""
    assert entry.superseded_by == ""
    assert entry.content_hash == _digest(entry.content)


def test_changed_value_creates_new_version_and_supersedes_old() -> None:
    """取值变化 ⇒ 新增 v2，旧版 superseded 并指回新版（不原地覆盖）。"""
    holder = {"facts": [KeyFact(entity="部署环境", value="生产集群 A")]}
    store = _store(holder)
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    first = _facts(store)[0]

    holder["facts"] = [KeyFact(entity="部署环境", value="生产集群 B")]
    store.write("L2", _episodic("e1", "s1"))
    store.compact(session_id="s1")

    chain = sorted(_facts(store), key=lambda entry: entry.version)
    assert [entry.id for entry in chain] == ["keyfact.部署环境", "keyfact.部署环境.v2"]
    old, new = chain
    assert old.status == "superseded"
    assert old.superseded_by == "keyfact.部署环境.v2"
    assert old.content == "部署环境: 生产集群 A", "旧值未被销毁"
    assert new.status == "active" and new.version == first.version + 1
    assert new.parent_id == first.id
    assert new.content == "部署环境: 生产集群 B"


def test_default_read_returns_latest_only() -> None:
    """缺省检索只见 active 链头；旧版不占预算、不被复用强化。"""
    holder = {"facts": [KeyFact(entity="部署环境", value="A")]}
    store = _store(holder)
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    # 旧版在被取代前先被复用一次（真实形态：它曾长期是活跃版本）⇒ 若过滤晚于预算，
    # 其复用加权会把它排到链头之前并吃掉预算。
    store.read("部署环境", budget=4096)

    holder["facts"] = [KeyFact(entity="部署环境", value="B")]
    store.write("L2", _episodic("e1", "s1"))
    store.compact(session_id="s1")
    old = next(entry for entry in _facts(store) if entry.id == "keyfact.部署环境")
    prior_reuse = old.reuse_count

    only_facts = {"exclude_source_prefixes": ("loop", "compaction")}
    # 先做紧预算检索：旧版复用加权仍在，若过滤晚于预算它会排到链头之前并挤掉链头。
    tight = [entry.id for entry in store.read("部署环境", budget=6, **only_facts)]
    assert tight == ["keyfact.部署环境.v2"], "旧版必须在预算分配前退出，否则会挤掉链头"
    assert old.reuse_count == prior_reuse, "被 supersede 的版本不参与检索强化"
    found = [entry.id for entry in store.read("部署环境", budget=4096, **only_facts)]
    assert found == ["keyfact.部署环境.v2"]


def test_audit_keeps_both_versions() -> None:
    """审计面保留全链，可追溯「当时为什么这么记」。"""
    holder = {"facts": [KeyFact(entity="部署环境", value="生产集群 A")]}
    store = _store(holder)
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    holder["facts"] = [KeyFact(entity="部署环境", value="生产集群 B")]
    store.write("L2", _episodic("e1", "s1"))
    store.compact(session_id="s1")

    assert {entry.id for entry in store.audit()} >= {
        "keyfact.部署环境",
        "keyfact.部署环境.v2",
    }


def test_unchanged_value_refreshes_in_place() -> None:
    """取值未变 ⇒ 就地刷新（幂等），条目不增长、版本不升。"""
    holder = {"facts": [KeyFact(entity="部署环境", value="生产集群 A")]}
    store = _store(holder)
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    first = _facts(store)[0]

    store.write("L2", _episodic("e1", "s1"))
    store.compact(session_id="s1")

    facts = _facts(store)
    assert [entry.id for entry in facts] == ["keyfact.部署环境"]
    assert facts[0].version == 1 and facts[0].status == "active"
    assert facts[0].ts == first.ts, "同值就地刷新保留首见时间戳"


def test_redacted_value_is_rewritten_in_place() -> None:
    """旧值被抹（`<redacted>`）⇒ 不算历史取值，就地重写而非升版（修复面不造悬空链头）。"""
    holder = {"facts": [KeyFact(entity="榴莲", value=REDACTED, ref="coeffect:secret")]}
    store = _store(holder)
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")

    holder["facts"] = [KeyFact(entity="榴莲", value="被称为水果之王")]
    store.write("L2", _episodic("e1", "s1"))
    store.compact(session_id="s1")

    facts = _facts(store)
    assert [entry.id for entry in facts] == ["keyfact.榴莲"]
    assert facts[0].version == 1 and facts[0].status == "active"
    assert facts[0].content == "榴莲: 被称为水果之王"


def test_rollback_of_second_compaction_restores_first_version() -> None:
    """回滚新版压实 ⇒ v2 删除、旧版恢复 active（取代可逆）。"""
    tracker = EffectTracker()
    holder = {"facts": [KeyFact(entity="部署环境", value="生产集群 A")]}
    store = _store(holder, tracker=tracker)
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")

    holder["facts"] = [KeyFact(entity="部署环境", value="生产集群 B")]
    store.write("L2", _episodic("e1", "s2"))
    store.compact(session_id="s2")
    assert "keyfact.部署环境.v2" in dict(store.index().entries)

    report = tracker.rollback("compaction.s2")

    assert report.undo_failed == []
    facts = {entry.id: entry for entry in _facts(store)}
    assert "keyfact.部署环境.v2" not in facts, "回滚新版 ⇒ v2 移除"
    assert facts["keyfact.部署环境"].status == "active", "旧版恢复可召回"
    assert facts["keyfact.部署环境"].superseded_by == ""


def test_content_hash_ignores_surrounding_whitespace() -> None:
    """写入自动计算哈希；仅首尾空白差异 ⇒ 同一哈希。"""
    store = MemoryStore()
    left = MemoryEntry(
        id="x1",
        layer="L2",
        content="  同一事实  ",
        tags=[],
        source="loop",
        trace_id="t",
    )
    right = MemoryEntry(
        id="x2",
        layer="L2",
        content="同一事实",
        tags=[],
        source="loop",
        trace_id="t",
    )

    store.write("L2", left)
    store.write("L2", right)

    assert left.content_hash == right.content_hash == _digest("同一事实")


def test_relation_same_triple_stays_single_entry() -> None:
    """关系 id 已编码完整三元组 ⇒ 同三元组覆盖即幂等，不生成版本链。"""
    store = MemoryStore(
        summarizer=lambda entries: "摘要：关系",
        relation_extractor=lambda entries: [Relation(head="A", predicate="depends_on", tail="B")],
    )
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    store.write("L2", _episodic("e1", "s2"))
    store.compact(session_id="s2")

    relations = [entry for entry in store.audit() if "relation" in entry.tags]
    assert [entry.id for entry in relations] == ["relation.a--depends_on--b"]
    assert relations[0].version == 1 and relations[0].status == "active"
