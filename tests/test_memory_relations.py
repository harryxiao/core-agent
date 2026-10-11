"""实体关系抽取（relations）单测：三元组落库 + 闭合谓词 + 密钥脱敏（fail-closed）。

对应规格：doc/openspec/specs/memory/spec.md「实体关系抽取（relations）」。
change 0203 / ADR-0193 / 账本 E140。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.context import DynamicAssembler
from core.memory import (
    REDACTED,
    MemoryEntry,
    MemoryStore,
    Relation,
    extract_relations_with,
    key_fact_cap,
    parse_relations,
    redact_secrets,
    relation_cap,
    scrub_relation,
)
from core.memory.backend import FileBackend
from core.plugin_registry import EffectTracker

# 密钥样例（**测试哨兵**，非真实凭据）：形态命中 `_SECRET_PATTERNS`
_SECRET = "sk-abcdefgh12345678"

# 长 id 锚的下界：3 × `slug(48)` 的 `relation.*` id 远超此值（`FileBackend` 无路径长度约束）
_LONG_ID_CHARS = 100


def _episodic(entry_id: str, session_id: str, content: str = "事件") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["loop"],
        source="loop",
        session_id=session_id,
        kind="episodic",
        trace_id="t",
    )


def _store(relations: list[Relation], *, session_id: str = "s1") -> MemoryStore:
    """构造注入了「定值关系抽取器」的 store（摘要器同注入，压实照常走完整流程）。"""
    store = MemoryStore(
        summarizer=lambda entries: "摘要：关系",
        relation_extractor=lambda entries: list(relations),
    )
    store.write("L2", _episodic("e0", session_id))
    return store


def _relations(store: MemoryStore) -> list[MemoryEntry]:
    return [entry for entry in store.audit() if "relation" in entry.tags]


# ---- 未接线 ----


def test_unwired_extractor_changes_nothing() -> None:
    """未注入抽取器（缺省）⇒ 无 `relation` 条目，摘要照常。"""
    store = MemoryStore(summarizer=lambda entries: "摘要：关系")
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert _relations(store) == [], "未注入 ⇒ 零抽取"
    assert store.summary_for("s1") is not None


def test_extraction_runs_without_summarizer() -> None:
    """抽取与摘要各自独立：未注入摘要器也能抽取（不写摘要条目）。"""
    store = MemoryStore(relation_extractor=lambda entries: [Relation("部署", "uses", "Docker")])
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert [e.id for e in _relations(store)] == ["relation.部署--uses--docker"]
    assert store.summary_for("s1") is None, "未注入摘要器 ⇒ 不写摘要条目"


# ---- 落库形态 ----


def test_happy_path_entry_shape() -> None:
    store = _store([Relation("service-a", "depends_on", "service-b")])

    store.compact(session_id="s1")

    entry = _relations(store)[0]
    assert entry.id == "relation.service-a--depends_on--service-b"
    assert entry.content == "service-a --depends_on--> service-b"
    assert entry.kind == "semantic"
    assert entry.source == "relation"
    assert entry.session_id == "", "全局层：跨会话长期知识"
    assert entry.trace_id == "compaction.s1"
    assert "relation" in entry.tags
    assert "entity:service-a" in entry.tags
    assert "entity:service-b" in entry.tags
    assert "predicate:depends_on" in entry.tags
    assert "session:s1" in entry.tags, "会话仅作溯源标注"


def test_chinese_predicate_normalized() -> None:
    """中文变体 ⇒ 归一化为**规范英文谓词**（`id` 与 `predicate:` 标注一并用规范值）。"""
    store = _store([Relation("订单服务", "依赖", "支付服务")])

    store.compact(session_id="s1")

    entry = _relations(store)[0]
    assert entry.id == "relation.订单服务--depends_on--支付服务", "中文谓词归一化"
    assert "predicate:depends_on" in entry.tags


@pytest.mark.parametrize(
    ("variant", "canonical"),
    [("依赖", "depends_on"), ("属于", "part_of"), ("导致", "causes"), ("使用", "uses")],
)
def test_predicate_variants_map_to_canonical(variant: str, canonical: str) -> None:
    """`scrub_relation` 把各中文变体归一化为规范英文谓词。"""
    cleaned, reason = scrub_relation(Relation("甲", variant, "乙"))
    assert reason == ""
    assert cleaned is not None
    assert cleaned.predicate == canonical


def test_same_triple_twice_is_idempotent() -> None:
    """同一三元组两次抽取 ⇒ 仍只有**一条**条目（同 `id` 覆盖式更新）。"""
    store = _store([Relation("a", "uses", "b")])
    store.compact(session_id="s1")
    store.compact(session_id="s1")

    assert [e.id for e in _relations(store)] == ["relation.a--uses--b"]


# ---- 丢弃与留痕 ----


def test_unknown_predicate_dropped_and_warned() -> None:
    """未知谓词 ⇒ 整条丢弃；留痕含实体名与**原始**谓词，不含取值。"""
    store = _store([Relation("甲", "吃掉", "乙")])

    with pytest.warns(RuntimeWarning) as record:
        store.compact(session_id="s1")

    assert _relations(store) == [], "未知谓词 ⇒ 不落库"
    message = str(record[0].message)
    assert "甲" in message
    assert "吃掉" in message, "留痕报原始谓词"


def test_secret_shaped_entity_dropped_with_redacted_warning() -> None:
    """密钥形状的 `head` ⇒ 整条丢弃；留痕中的实体名**已脱敏**（不回显明文）。"""
    store = _store([Relation(_SECRET, "uses", "乙")])

    with pytest.warns(RuntimeWarning) as record:
        store.compact(session_id="s1")

    assert _relations(store) == [], "密钥形状 ⇒ fail-closed"
    message = str(record[0].message)
    assert _SECRET not in message, "留痕不得回显明文密钥"
    assert REDACTED in message


def test_secret_shaped_tail_dropped() -> None:
    store = _store([Relation("甲", "uses", _SECRET)])

    with pytest.warns(RuntimeWarning):
        store.compact(session_id="s1")

    assert _relations(store) == []


@pytest.mark.parametrize(("head", "tail"), [("", "乙"), ("甲", ""), ("  ", "乙")])
def test_empty_entity_dropped(head: str, tail: str) -> None:
    cleaned, reason = scrub_relation(Relation(head, "uses", tail))
    assert cleaned is None
    assert reason == "empty"


def test_redact_secrets_is_the_single_criterion() -> None:
    """留痕脱敏与关键事实**同源**：命中即替换（判据一处定义）。"""
    assert _SECRET not in redact_secrets(_SECRET)
    assert REDACTED in redact_secrets(_SECRET)


# ---- 有界 ----


def test_cap_bounds_batch_matching_key_fact_cap() -> None:
    """落库条数受 `relation_cap(n)` 界住，且与 `key_fact_cap` **同一把旋钮**。"""
    over = 40
    store = _store([Relation(f"实体{i}", "uses", f"目标{i}") for i in range(over)])

    store.compact(session_id="s1")

    assert len(_relations(store)) == relation_cap(1), "1 条材料 ⇒ cap(1)"
    assert relation_cap is key_fact_cap, "同一把调参旋钮（别名、非副本）"


# ---- 不遮蔽 / 回滚 / 注入面 ----


def test_relations_not_in_compaction_material() -> None:
    """`kind="semantic"` ⇒ 关系**不回喂**压实材料（材料面只收 `kind="episodic"`）。"""
    store = _store([Relation("a", "uses", "b")])
    store.compact(session_id="s1")

    # 材料源的唯一入口，直测最精确（私有面：ruff SLF001 + pyright reportPrivateUsage 双抑制）
    material = store._episodic_groups("s1")  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    ids = {str(entry.id) for entries in material.values() for entry in entries}
    assert "relation.a--uses--b" not in ids


def test_relations_rollback_with_compaction() -> None:
    """关系与压实**同 trace** ⇒ 回滚 `compaction.<key>` 连带撤销关系。"""
    tracker = EffectTracker()
    store = MemoryStore(
        effect_tracker=tracker,
        summarizer=lambda entries: "摘要：关系",
        relation_extractor=lambda entries: [Relation("a", "uses", "b")],
    )
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    assert [e.id for e in _relations(store)] == ["relation.a--uses--b"]

    tracker.rollback("compaction.s1")

    assert _relations(store) == [], "回滚压实 ⇒ 关系一并撤销"


def test_relations_reach_the_fact_face() -> None:
    """事实面按 `source` 前缀排除压实产物 ⇒ `source="relation"` **自动进入**。"""
    store = _store([Relation("a", "uses", "b")])
    store.compact(session_id="s1")

    assembler = DynamicAssembler(memory=store, exclude_fact_sources=("compaction",))
    contents = [fact["content"] for fact in assembler.build("t", "reason", budget=4096).facts]
    assert any("a --uses--> b" in content for content in contents), "关系须在事实面"


# ---- 长 id 与解析 ----


def test_long_id_round_trips_through_file_backend(tmp_path: Path) -> None:
    """3 × `slug(48)` 的长 `id` 经 `FileBackend` 往返 —— id 是 JSONL **字段**（非文件名）。"""
    head = "长" * 60
    tail = "尾" * 60
    path = tmp_path / "mem.jsonl"
    store = MemoryStore(
        backend=FileBackend(path),
        relation_extractor=lambda entries: [Relation(head, "uses", tail)],
    )
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    relation_id = _relations(store)[0].id
    assert len(relation_id) > _LONG_ID_CHARS, "本锚的前提：长 id"

    reloaded = MemoryStore(backend=FileBackend(path))

    assert reloaded.audit(), "重载后库非空"
    assert any(entry.id == relation_id for entry in reloaded.audit()), "长 id 往返成功"


def test_parse_relations_tolerates_fences_and_skips_bad_elements() -> None:
    text = """```json
    [
      {"head": "a", "predicate": "uses", "tail": "b"},
      {"head": "缺尾"},
      "not-an-object"
    ]
    ```"""
    assert [(r.head, r.predicate, r.tail) for r in parse_relations(text)] == [("a", "uses", "b")]
    assert parse_relations("no json here") == []


def test_extract_relations_with_warns_on_unparseable_output() -> None:
    """模型有输出但无可解析数组 ⇒ 留痕（只报长度，不含正文）。"""
    extractor = extract_relations_with(lambda prompt: "抱歉，我无法抽取")

    with pytest.warns(RuntimeWarning) as record:
        assert extractor([_episodic("e0", "s1")]) == []

    assert "抱歉" not in str(record[0].message), "留痕不含模型输出正文"
