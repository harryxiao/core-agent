"""相关性打分（memory）。

``relevance = w1·sim + w2·freshness + w3·log(1+reuse) + w4·layer_priority``。
``sim`` 默认词法相似（token 重叠，离线可测）；注入 ``embedder``（如
llm-provider 的向量化）则升级为余弦相似，embedder 失败降级回词法。

对应接口：doc/03-interfaces/memory-interface.md §3
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable

from .protocol import Layer, MemoryEntry

# 层优先级：L0 元策略 > L3 技能 > L2 事实 > L1 索引 > L4 归档
_LAYER_PRIORITY: dict[Layer, float] = {"L0": 1.0, "L1": 0.4, "L2": 0.6, "L3": 0.8, "L4": 0.2}

# 权重：语义相似 / 新鲜度 / 复用频次 / 层优先级
_W_SIM = 0.5
_W_FRESH = 0.1
_W_REUSE = 0.2
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


def relevance(
    entry: MemoryEntry,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]] | None = None,
) -> float:
    """计算条目相对查询的相关性得分（越高越相关）。"""
    sim = _similarity(entry, query, embedder)
    freshness = _freshness(entry)
    reuse = math.log1p(entry.reuse_count)
    layer_priority = _LAYER_PRIORITY[entry.layer]
    return _W_SIM * sim + _W_FRESH * freshness + _W_REUSE * reuse + _W_LAYER * layer_priority


def _similarity(
    entry: MemoryEntry,
    query: str,
    embedder: Callable[[list[str]], list[list[float]]] | None,
) -> float:
    if embedder is not None:
        try:
            vectors = embedder([entry.content, query])
            return _cosine(vectors[0], vectors[1])
        except Exception:  # noqa: BLE001 — embedder 失败降级词法
            pass
    return _lexical_sim(entry, query)


def _lexical_sim(entry: MemoryEntry, query: str) -> float:
    query_tokens = tokens(query)
    if not query_tokens:
        return 0.0
    return len(tokens(entry.content) & query_tokens) / len(query_tokens)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _freshness(entry: MemoryEntry) -> float:
    if entry.ts <= 0:
        return 0.0
    age = max(0.0, time.time() - entry.ts)
    return 1.0 / (1.0 + age / 86400.0)  # 按天衰减
