"""PA-09 E：词法 vs 语义检索离线基准（change 0289 / ADR-0279 / 台账 E225）。

**基准而非模型评测**：用一个确定性的「概念/同义词」embedder，让改写查询与 gold 条目
**词面零重叠、概念完全一致**，从而把「注入向量后排序是否真的按语义走」变成可复现数字。

- 20 组互不重叠的同义词域；每组：
  - 查询 `q1 q2 q3`；
  - gold `g1 g2 g3`（与查询同概念，词面零重叠）；
  - 干扰 `q1 d q3`（与查询共享 2 个词面，但第 2 个概念不同）。
- 词法 store（无 embedder，BM25）预期干扰排前；语义 store（`ConceptEmbedder`）预期 gold 排前。
- 纯离线、无网络、无第三方依赖。

**局限**：假 embedder 证明的是通路与量纲，**不**证明真实模型质量；真实模型质量须在线测量。
"""

from __future__ import annotations

import re

from core.memory import IndexEntry, Layer, MemoryEntry, MemoryStore

_TOP_K = 5
_MRR_MARGIN = 0.5  # 语义相对词法的 MRR 最低增益
_SEMANTIC_RECALL1_MIN = 0.9
_SEMANTIC_MRR_MIN = 0.9

# (查询表面 1/2/3, gold 同义表面 1/2/3, 干扰第 2 词)；四组概念彼此独立。
_CASES: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("vehicle", "repair", "manual", "automobile", "maintenance", "handbook", "washing"),
    ("doctor", "medicine", "hospital", "physician", "drug", "clinic", "billing"),
    ("teacher", "lesson", "student", "instructor", "class", "pupil", "grading"),
    ("engine", "fuel", "filter", "motor", "petrol", "strainer", "cooling"),
    ("garden", "soil", "seed", "yard", "earth", "kernel", "watering"),
    ("kitchen", "oven", "recipe", "galley", "stove", "formula", "cleaning"),
    ("library", "book", "shelf", "archive", "volume", "rack", "cataloging"),
    ("music", "guitar", "concert", "melody", "banjo", "recital", "rehearsal"),
    ("travel", "ticket", "hotel", "journey", "pass", "inn", "luggage"),
    ("finance", "bank", "loan", "budget", "treasury", "credit", "auditing"),
    ("weather", "rain", "forecast", "climate", "precipitation", "projection", "humidity"),
    ("painting", "brush", "gallery", "canvas", "pencil", "museum", "framing"),
    ("computer", "keyboard", "software", "processor", "typewriter", "program", "network"),
    ("farm", "crop", "tractor", "ranch", "harvest", "plow", "irrigation"),
    ("ocean", "coral", "fish", "sea", "reef", "trout", "current"),
    ("mountain", "trail", "climber", "peak", "path", "hiker", "avalanche"),
    ("camera", "photo", "album", "lens", "image", "portfolio", "shutter"),
    ("bakery", "bread", "flour", "patisserie", "loaf", "grain", "frosting"),
    ("election", "candidate", "ballot", "vote", "nominee", "poll", "campaign"),
    ("factory", "machine", "worker", "plant", "device", "employee", "safety"),
)

_WORD = re.compile(r"[a-z]+")


def _concept_table() -> dict[str, int]:
    """词 → 概念维：同义词共享维；20 组 × 4 维互不相同。"""
    table: dict[str, int] = {}
    for case_index, (q1, q2, q3, g1, g2, g3, d2) in enumerate(_CASES):
        base = case_index * 4
        table[q1] = table[g1] = base
        table[q2] = table[g2] = base + 1
        table[q3] = table[g3] = base + 2
        table[d2] = base + 3
    return table


_CONCEPTS = _concept_table()
_DIM = len(_CASES) * 4


def _concept_embed(text: str) -> list[float]:
    """确定性概念向量：按词计数到概念维（未登录词忽略）。"""
    vector = [0.0] * _DIM
    for word in _WORD.findall(text.lower()):
        concept = _CONCEPTS.get(word)
        if concept is not None:
            vector[concept] += 1.0
    return vector


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


def _entry(entry_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="bench",
        trace_id="bench",
        ts=0.0,
    )


def _batch_embed(texts: list[str]) -> list[list[float]]:
    return [_concept_embed(text) for text in texts]


def _build_store(*, semantic: bool) -> MemoryStore:
    backend = _InMemoryBackend()
    store = MemoryStore(backend=backend, embedder=_batch_embed if semantic else None)
    for index, (q1, _q2, q3, g1, g2, g3, d2) in enumerate(_CASES):
        store.write("L2", _entry(f"gold-{index:02d}", f"{g1} {g2} {g3}"))
        store.write("L2", _entry(f"distractor-{index:02d}", f"{q1} {d2} {q3}"))
    return store


def _query(index: int) -> str:
    q1, q2, q3, _, _, _, _ = _CASES[index]
    return f"{q1} {q2} {q3}"


def _metrics(store: MemoryStore) -> tuple[float, float, float]:
    """返回 (recall@1, recall@5, MRR@5)。"""
    top1 = top5 = 0
    reciprocal_ranks: list[float] = []
    for index in range(len(_CASES)):
        rows = store.read(_query(index), budget=100_000)
        ids = [entry.id for entry in rows[:_TOP_K]]
        gold = f"gold-{index:02d}"
        if ids and ids[0] == gold:
            top1 += 1
        if gold in ids:
            top5 += 1
            reciprocal_ranks.append(1.0 / (ids.index(gold) + 1))
        else:
            reciprocal_ranks.append(0.0)
    total = len(_CASES)
    return top1 / total, top5 / total, sum(reciprocal_ranks) / total


def test_lexical_ranking_misses_paraphrase() -> None:
    """词法基线：干扰项共享词面 ⇒ gold 不进 top-1（机制性断言，不依赖随机）。"""
    recall1, recall5, mrr = _metrics(_build_store(semantic=False))
    print(f"lexical: recall@1={recall1:.3f} recall@5={recall5:.3f} mrr@5={mrr:.3f}")  # noqa: T201

    assert recall1 == 0.0
    assert mrr < _MRR_MARGIN


def test_semantic_ranking_recovers_paraphrase() -> None:
    """语义通路：同概念向量把 gold 排到第一。"""
    recall1, recall5, mrr = _metrics(_build_store(semantic=True))
    print(f"semantic: recall@1={recall1:.3f} recall@5={recall5:.3f} mrr@5={mrr:.3f}")  # noqa: T201

    assert recall1 >= _SEMANTIC_RECALL1_MIN
    assert recall5 == 1.0
    assert mrr >= _SEMANTIC_MRR_MIN


def test_semantic_gain_over_lexical_is_large() -> None:
    """同一语料、同一查询：语义 MRR 显著高于词法（基准的裁决面）。"""
    lexical = _metrics(_build_store(semantic=False))
    semantic = _metrics(_build_store(semantic=True))

    assert semantic[2] - lexical[2] >= _MRR_MARGIN


def test_benchmark_corpus_is_deterministic() -> None:
    """概念表与向量无随机源：两次构造逐项一致。"""
    first = [(word, _concept_embed(word)) for word in sorted(_CONCEPTS)]
    second = [(word, _concept_embed(word)) for word in sorted(_CONCEPTS)]

    assert first == second
