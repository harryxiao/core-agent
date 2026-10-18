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
from collections.abc import Callable, Iterable, MutableMapping, Sequence
from dataclasses import dataclass

from .protocol import Layer, MemoryEntry

# 层优先级：L0 元策略 > L3 技能 > L2 事实 > L1 索引 > L4 归档
_LAYER_PRIORITY: dict[Layer, float] = {"L0": 1.0, "L1": 0.4, "L2": 0.6, "L3": 0.8, "L4": 0.2}

# 加性权重：语义相似 / 层优先级 / 内容分区（时间·复用·重要度改由 ``rank`` 乘性调制）
_W_SIM = 0.5
_W_LAYER = 0.2
_W_TIER = 0.15

# 内容分区标签（change 0277 / ADR-0267）：精确小写匹配；未知标签/无标签 ⇒ 默认档。
# 冲突（高低档同时命中）⇒ 高档优先；只看 tags，不从 source/kind 推断。
# 档位取 {+1, 0, −1}（默认档为零）：rank 会乘复用/重要度调制，默认档若取常量偏移会
# 抬高全部无标签条目的基数，令高复用填充项反超 gold（0275 基准实测 recall 1.000 → 0.45）。
_TIER_HIGH_TAGS = frozenset({"milestone", "decision"})
_TIER_LOW_TAGS = frozenset({"log", "transcript"})

# 一次检索的向量化批大小（change 0290 / ADR-0280）：候选数 N ⇒ 调用数 ceil((N+1)/64)。
_SIM_BATCH_SIZE = 64

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


def _chunk_similarities(
    content_ids: Sequence[str],
    content_vectors: Sequence[list[float]],
    query_vec: list[float],
) -> dict[str, float] | None:
    """一块内容的余弦映射；数量 / 维度不符 ⇒ ``None``。"""
    if len(content_vectors) != len(content_ids):
        return None
    sims: dict[str, float] = {}
    for entry_id, vector in zip(content_ids, content_vectors, strict=True):
        if len(vector) != len(query_vec):
            return None
        sims[entry_id] = _cosine(vector, query_vec)
    return sims


def batch_similarities(
    entries: Sequence[MemoryEntry],
    query: str,
    embedder: Callable[[list[str]], list[list[float]]],
    *,
    batch_size: int = _SIM_BATCH_SIZE,
) -> dict[str, float] | None:
    """一次检索的余弦相似映射（change 0290 / ADR-0280）。

    - 空候选集返回 ``{}`` 且**不调用** embedder（避免空读的瞬时失败置粘性降级）。
    - ``query`` 恒在第一批 ⇒ 每次检索至多向量化一次；每批一次 embedder 调用。
    - 任一批异常 / 数量不符 / 维度不符 ⇒ ``None``（本次检索**整体**降级词法，
      不返回部分映射，避免余弦与词法混合尺度）。
    """
    if not entries:
        return {}
    return _batched_cosine(entries, query, embedder, batch_size)


def _batched_cosine(
    entries: Sequence[MemoryEntry],
    query: str,
    embedder: Callable[[list[str]], list[list[float]]],
    batch_size: int,
) -> dict[str, float] | None:
    texts = [query, *(entry.content for entry in entries)]
    ids = [entry.id for entry in entries]
    sims: dict[str, float] = {}
    query_vec: list[float] | None = None
    try:
        for start in range(0, len(texts), batch_size):
            chunk = texts[start : start + batch_size]
            vectors = embedder(chunk)
            if len(vectors) != len(chunk):
                return None
            if start == 0:  # 第一批含 query，其向量作为后续所有块的比较基准
                query_vec = vectors[0]
                content_ids = ids[: len(vectors) - 1]
                content_vectors = vectors[1:]
            else:
                content_ids = ids[start - 1 : start - 1 + len(vectors)]
                content_vectors = vectors
            chunk_sims = (
                None
                if query_vec is None
                else _chunk_similarities(content_ids, content_vectors, query_vec)
            )
            if chunk_sims is None:
                return None
            sims.update(chunk_sims)
    except Exception:  # noqa: BLE001 — 任一失败 ⇒ 本次检索整体降级词法
        return None
    return sims


def relevance(
    entry: MemoryEntry,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
    *,
    stats: LexicalStats | None = None,
    sim: float | None = None,
) -> float:
    """**语义相似 × 层结构权重**（加性项；越高越相关）。

    时间 / 复用 / 重要度不在此处——由 :func:`rank` 乘性调制，避免与加性项双重计数。
    ``stats`` 仅用于 embedder 缺省/失败时的词法打分；``None`` ⇒ 原重叠公式（兼容面）。
    ``sim`` 为预计算相似度（:func:`batch_similarities`），提供时优先于 ``embedder``；
    ``0.0`` 与负余弦是合法值，故用 ``is None`` 而非真值判断。
    """
    if sim is None:
        sim = _similarity(entry, query, embedder, stats)
    return _W_SIM * sim + _W_LAYER * _LAYER_PRIORITY[entry.layer] + _W_TIER * _tier_weight(entry)


def _tier_weight(entry: MemoryEntry) -> float:
    """内容分区权重：高档 +1.0 / 默认 0.0 / 低档 −1.0（冲突高档优先）。"""
    for tag in entry.tags:
        if tag in _TIER_HIGH_TAGS:
            return 1.0
    for tag in entry.tags:
        if tag in _TIER_LOW_TAGS:
            return -1.0
    return 0.0


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
    sim: float | None = None,
) -> float:
    """检索排序得分：``relevance · recency_decay · (1 + log1p(reuse)) · (1 + importance)``。"""
    return (
        relevance(entry, query, embedder, stats=stats, sim=sim)
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
