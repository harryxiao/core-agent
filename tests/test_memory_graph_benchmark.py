"""PA-09 D：多跳检索与关系流水线离线基准（change 0289 / ADR-0279 / 台账 E225）。

**只测不改产品**：关系三元组当前以扁平 L2 条目落库（tags 含 `entity:` / `predicate:`），
没有邻接索引与遍历 API。本基准回答「若做 1 跳邻接扩展，第二跳 gold 能否被捞回」：

- 20 条合成链：`Z{i} --owns--> B{i}`、`B{i} --part_of--> C{i}`；
- 查询只含 `Z{i}` 与自然语言词，**第二跳 gold 与查询零词面重叠**；
- 扁平基线（BM25 top-5）预期 **漏掉** gold；
- 测试内从首跳结果的 `entity:` 标签建 1 跳邻接，把邻居提升到候选前部，预期 **召回** gold。

另度量关系**确定性流水线**的覆盖率：白名单谓词 / 未知谓词 / 空实体 / 同批重复 / 密钥形态 /
名额上限。**不测 LLM 抽取质量**（离线无法测），该局限由 ADR-0279 登记。
"""

from __future__ import annotations

from collections import defaultdict

from core.memory import IndexEntry, Layer, MemoryEntry, MemoryStore
from core.memory.extract import (
    RELATION_PREDICATES,
    Relation,
    normalize_predicate,
    relation_cap,
    slug_entity,
)
from core.memory.relevance import tokens
from core.memory.store import _plan_relations

_CHAINS = 20
_TOP_K = 5
_EXPECTED_CAP = 8  # ceil(30 × 0.25) = 8 ⇒ 落在 KEY_FACTS_MIN=8


class _InMemoryBackend:
    """最小后端：`search` 返回全部条目（排序完全交给 `MemoryStore.read`）。"""

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}

    def get(self, layer: Layer, entry_id: str) -> MemoryEntry | None:
        return self._entries.get(entry_id)

    def put(self, entry: MemoryEntry) -> str:
        self._entries[entry.id] = entry
        return entry.id

    def search(self, query: str, layer: Layer | None = None) -> list[MemoryEntry]:
        return list(self._entries.values())

    def list_index(self) -> IndexEntry:
        return IndexEntry(entries=[])

    def delete(self, entry_id: str) -> None:
        self._entries.pop(entry_id, None)


def _relation(head: str, predicate: str, tail: str) -> MemoryEntry:
    head_slug = slug_entity(head)
    tail_slug = slug_entity(tail)
    return MemoryEntry(
        id=f"relation.{head_slug}--{predicate}--{tail_slug}",
        layer="L2",
        content=f"{head} --{predicate}--> {tail}",
        tags=[
            "relation",
            f"entity:{head_slug}",
            f"entity:{tail_slug}",
            f"predicate:{predicate}",
        ],
        source="relation",
        trace_id="bench",
        ts=0.0,
        kind="semantic",
    )


def _chain_entries(index: int) -> list[MemoryEntry]:
    z = f"Z{index:02d}"
    b = f"B{index:02d}"
    c = f"C{index:02d}"
    return [
        _relation(z, "owns", b),  # 首跳（seed）
        _relation(b, "part_of", c),  # 第二跳（gold）
        _relation(z, "uses", f"D{index:02d}"),  # 同头干扰
        _relation(z, "depends_on", f"E{index:02d}"),  # 同头干扰
        # 共享词面干扰：内容含 `component` 词元，但实体 slug 是 `component-NN`，
        # 不会成为查询实体（避免把词面噪声误当图入口）。
        _relation(f"component-{index:02d}", "part_of", f"group{index:02d}"),
    ]


def _build_store() -> MemoryStore:
    store = MemoryStore(backend=_InMemoryBackend())
    for index in range(_CHAINS):
        for entry in _chain_entries(index):
            store.write("L2", entry)
    return store


def _query(index: int) -> str:
    return f"which group holds the component owned by Z{index:02d}"


def _adjacency(entries: list[MemoryEntry]) -> dict[str, set[str]]:
    """测试内邻接：实体 slug → 含该实体的条目 id（等价于轻图的 1 跳表）。"""
    adjacency: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        for tag in entry.tags:
            if tag.startswith("entity:"):
                adjacency[tag[len("entity:") :]].add(entry.id)
    return adjacency


def _query_entities(query: str, entries: list[MemoryEntry]) -> set[str]:
    """查询词元 ∩ 关系条目的 `entity:` 标签（轻图的入口节点）。"""
    query_tokens = tokens(query)
    roots: set[str] = set()
    for entry in entries:
        for tag in entry.tags:
            if tag.startswith("entity:") and tag[len("entity:") :] in query_tokens:
                roots.add(tag[len("entity:") :])
    return roots


def _graph_order(
    ranked: list[MemoryEntry],
    adjacency: dict[str, set[str]],
    entries: list[MemoryEntry],
    query: str,
) -> list[MemoryEntry]:
    """轻图形态：从查询实体出发做 2 跳 BFS（tags 邻接），已发现条目在前，其余按扁平序。"""
    by_id = {entry.id: entry for entry in entries}
    frontier = _query_entities(query, entries)
    discovered: list[str] = []
    visited: set[str] = set()
    for _ in range(2):
        next_frontier: set[str] = set()
        for entity in sorted(frontier):
            for entry_id in sorted(adjacency.get(entity, set())):
                if entry_id in visited:
                    continue
                visited.add(entry_id)
                discovered.append(entry_id)
                for tag in by_id[entry_id].tags:
                    if tag.startswith("entity:"):
                        next_frontier.add(tag[len("entity:") :])
        frontier = next_frontier
    seen = set(discovered)
    return [by_id[entry_id] for entry_id in discovered] + [
        entry for entry in ranked if entry.id not in seen
    ]


def test_flat_retrieval_misses_second_hop() -> None:
    """扁平 BM25：首跳占满 top-5，第二跳 gold 全部漏掉。"""
    store = _build_store()
    hits = 0
    for index in range(_CHAINS):
        rows = store.read(_query(index), budget=100_000)
        ids = [entry.id for entry in rows[:_TOP_K]]
        gold = f"relation.b{index:02d}--part_of--c{index:02d}"
        hits += gold in ids
    recall = hits / _CHAINS
    print(f"flat: second_hop_recall@5={recall:.3f}")  # noqa: T201

    assert recall == 0.0


def test_one_hop_expansion_recovers_second_hop() -> None:
    """模拟轻图：从首跳实体做 1 跳扩展 ⇒ 第二跳 gold 进入 top-5。"""
    store = _build_store()
    all_entries = store.audit(None)
    adjacency = _adjacency(list(all_entries))
    hits = 0
    for index in range(_CHAINS):
        query = _query(index)
        ranked = store.read(query, budget=100_000)
        ids = [
            entry.id
            for entry in _graph_order(list(ranked), adjacency, list(all_entries), query)[:_TOP_K]
        ]
        gold = f"relation.b{index:02d}--part_of--c{index:02d}"
        hits += gold in ids
    recall = hits / _CHAINS
    print(f"graph: second_hop_recall@5={recall:.3f}")  # noqa: T201

    assert recall == 1.0


def test_query_entity_resolves_to_first_hop_facts() -> None:
    """邻接扩展的前提：查询实体能定位到首跳事实（不靠 top-1 的浮点巧合）。"""
    store = _build_store()
    entries = list(store.audit(None))
    adjacency = _adjacency(entries)
    for index in range(_CHAINS):
        roots = _query_entities(_query(index), entries)
        assert roots == {f"z{index:02d}"}
        first_hop = {entry_id for entity in roots for entry_id in adjacency.get(entity, set())}
        assert first_hop == {
            f"relation.z{index:02d}--owns--b{index:02d}",
            f"relation.z{index:02d}--uses--d{index:02d}",
            f"relation.z{index:02d}--depends_on--e{index:02d}",
        }


def test_relation_pipeline_coverage() -> None:
    """确定性后处理：合法项保留、未知谓词/空实体/密钥形态丢弃、同批重复归并。"""
    valid = [Relation(f"H{index}", "uses", f"T{index}") for index in range(6)]
    raw = [
        *valid,
        Relation("A", "likes", "B"),  # 未知谓词
        Relation("", "uses", "X"),  # 空实体
        Relation("H0", "调用", "T0"),  # 与 H0 同三元组（归一化后重复）
        Relation("sk-" + "a" * 24, "uses", "Y"),  # 密钥形态
        Relation("Z", "相关", "W"),  # 中文变体 → related_to
    ]
    plan, secrets, unknown = _plan_relations(raw, cap=16)

    assert len(plan) == len(valid) + 1
    assert len(unknown) == 1
    assert len(secrets) == 1
    assert {relation.predicate for relation in plan} == {"uses", "related_to"}


def test_relation_pipeline_respects_cap() -> None:
    """名额上限：超额候选按声明顺序截断（cap 与关键事实同源）。"""
    raw = [Relation(f"H{index}", "uses", f"T{index}") for index in range(30)]
    cap = relation_cap(len(raw))
    plan, _, _ = _plan_relations(raw, cap=cap)

    assert len(plan) == cap
    assert cap == _EXPECTED_CAP
    print(f"relation_pipeline: kept={len(plan)} candidates={len(raw)} cap={cap}")  # noqa: T201


def test_predicate_allowlist_is_total_over_declared_variants() -> None:
    """闭合白名单覆盖率：每个声明的中英变体都能归一；未声明变体一律拒绝。"""
    coverage = sum(
        normalize_predicate(variant) == canonical
        for variant, canonical in RELATION_PREDICATES.items()
    )
    total = len(RELATION_PREDICATES)
    print(f"predicate_allowlist: normalized={coverage}/{total}")  # noqa: T201

    assert coverage == total
    assert normalize_predicate("likes") == ""
