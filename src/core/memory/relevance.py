"""相关性打分（memory）。

排序得分 ``rank`` 两部分构成——**语义/结构**（加性）与 **时间/复用/重要度**（乘性）：:

    rank = (_W_SIM·sim + _W_LAYER·layer_priority)
           · recency_decay · (1 + log1p(reuse_count)) · (1 + importance)

``sim`` 默认词法相似（token 重叠，离线可测）；注入 ``embedder``（如 llm-provider 的
向量化）则升级为余弦相似，embedder 失败降级回词法。

对应接口：doc/03-interfaces/memory-interface.md §3
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass

from .protocol import Layer, MemoryEntry

# 层优先级：L0 元策略 > L3 技能 > L2 事实 > L1 索引 > L4 归档
_LAYER_PRIORITY: dict[Layer, float] = {"L0": 1.0, "L1": 0.4, "L2": 0.6, "L3": 0.8, "L4": 0.2}

# 加性权重：语义相似 / 层优先级（时间·复用·重要度改由 ``rank`` 乘性调制）
_W_SIM = 0.5
_W_LAYER = 0.2

# 检索分词：非中文词元沿用 \w+ 语义（排除汉字，保留其他 Unicode 词字符），
# 连续汉字另按二元组切分——中文无空格，整句 \w+ / split() 会退化成单一词元，
# 令中文检索近乎零召回。
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[^\W\u4e00-\u9fff]+")


def tokens(text: str) -> set[str]:
    """检索分词：非中文词元 + 中文二元组（提高中文 query/content 重叠召回）。"""
    out = set(_WORD.findall(text.lower()))
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            out.add(run)
        else:
            out.update(run[i : i + 2] for i in range(len(run) - 1))
    return out


@dataclass(frozen=True)
class LexicalStats:
    """一次检索的语料统计（BM25 词法打分用；change 0252 / ADR-0242）。

    ``idf`` 只含查询词元（内存有界于 query 长度）；``doc_tokens`` 缓存候选条目的词元集，
    让排序阶段不重复分词。``stats`` 只对**构建它的那个 query** 有意义。
    """

    idf: dict[str, float]
    avg_len: float
    doc_tokens: dict[str, frozenset[str]]
    query_tokens: frozenset[str]
    k1: float = 1.2
    b: float = 0.75


def build_lexical_stats(
    entries: Iterable[MemoryEntry],
    query: str,
    *,
    token_cache: MutableMapping[str, tuple[str, frozenset[str]]] | None = None,
) -> LexicalStats | None:
    """对候选集做一次分词与文档频率统计；空查询 / 空语料 ⇒ ``None``（走原重叠公式）。

    ``token_cache``（change 0276 / ADR-0266）：``id → (content, 词元集)``。内容未变则复用
    词元集，同 id 覆写不同内容时自动失效并重新分词；缺省 ``None`` ⇒ 行为与既有逐字一致。
    """
    query_tokens = frozenset(tokens(query))
    if not query_tokens:
        return None
    doc_tokens: dict[str, frozenset[str]] = {}
    for entry in entries:
        cached = token_cache.get(entry.id) if token_cache is not None else None
        if cached is not None and cached[0] == entry.content:
            doc_tokens[entry.id] = cached[1]
            continue
        token_set = frozenset(tokens(entry.content))
        doc_tokens[entry.id] = token_set
        if token_cache is not None:
            token_cache[entry.id] = (entry.content, token_set)
    if not doc_tokens:
        return None
    total = len(doc_tokens)
    idf = {
        token: math.log(1.0 + (total - count + 0.5) / (count + 0.5))
        for token in query_tokens
        for count in [sum(1 for doc in doc_tokens.values() if token in doc)]
    }
    avg_len = max(1.0, sum(len(doc) for doc in doc_tokens.values()) / total)
    return LexicalStats(
        idf=idf,
        avg_len=avg_len,
        doc_tokens=doc_tokens,
        query_tokens=query_tokens,
    )


def relevance(
    entry: MemoryEntry,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
    *,
    stats: LexicalStats | None = None,
) -> float:
    """**语义相似 × 层结构权重**（加性项；越高越相关）。

    时间 / 复用 / 重要度不在此处——由 :func:`rank` 乘性调制，避免与加性项双重计数。
    ``stats`` 仅用于 embedder 缺省/失败时的词法打分；``None`` ⇒ 原重叠公式（兼容面）。
    """
    sim = _similarity(entry, query, embedder, stats)
    return _W_SIM * sim + _W_LAYER * _LAYER_PRIORITY[entry.layer]


def recency_decay(entry: MemoryEntry) -> float:
    """新鲜度衰减 ∈ (0,1]：``1/(1 + age/天)``；时间戳缺省（<=0）视为未知、不惩罚。"""
    if entry.ts <= 0:
        return 1.0
    age = max(0.0, time.time() - entry.ts)
    return 1.0 / (1.0 + age / 86400.0)


def rank(
    entry: MemoryEntry,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
    *,
    stats: LexicalStats | None = None,
) -> float:
    """检索排序得分：``relevance · recency_decay · (1 + log1p(reuse)) · (1 + importance)``。"""
    return (
        relevance(entry, query, embedder, stats=stats)
        * recency_decay(entry)
        * (1.0 + math.log1p(entry.reuse_count))
        * (1.0 + entry.importance)
    )


def _similarity(
    entry: MemoryEntry,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]] | None,
    stats: LexicalStats | None,
) -> float:
    if embedder is not None:
        try:
            vectors = embedder([entry.content, query])
            return _cosine(vectors[0], vectors[1])
        except Exception:  # noqa: BLE001 — embedder 失败降级词法
            pass
    return _lexical_sim(entry, query, stats)


def _lexical_sim(entry: MemoryEntry, query: str, stats: LexicalStats | None = None) -> float:
    """词法相似度：``stats`` 缺省为原重叠公式，否则 BM25（二值 tf + IDF + 长度归一）。

    BM25 项为 ``idf · (k1+1) / (1 + k1 · (1 - b + b · dl/avgdl))``，按查询 IDF 总和归一
    （短文档因子可 >1，故收顶 1.0）。罕见词元权重更高、长文档被长度惩罚。
    """
    if stats is None:
        query_tokens = tokens(query)
        if not query_tokens:
            return 0.0
        return len(tokens(entry.content) & query_tokens) / len(query_tokens)
    doc_tokens = stats.doc_tokens.get(entry.id)
    if doc_tokens is None:
        doc_tokens = frozenset(tokens(entry.content))
    total = sum(stats.idf.values())
    if total <= 0:
        return 0.0
    length_norm = stats.k1 * (1.0 - stats.b + stats.b * len(doc_tokens) / stats.avg_len)
    score = sum(
        stats.idf[token] * (stats.k1 + 1.0) / (1.0 + length_norm)
        for token in stats.query_tokens
        if token in doc_tokens and token in stats.idf
    )
    return min(1.0, score / total)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
