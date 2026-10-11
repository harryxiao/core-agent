"""记忆系统（L2，能力可调）。

L0-L4 分层记忆、热/冷温度检索、无行动不记忆、结晶/溶解、可逆写入；
``MemoryStore`` / ``Crystallizer`` 为具体类（实现 Plugin 契约），
``MemoryBackend`` 保持 Protocol（可插拔后端）。

对应规格：doc/openspec/specs/memory/spec.md
"""

from .backend import FileBackend
from .crystallizer import Crystallizer, PluginCandidate
from .embedding import batch_embed
from .extract import (
    KEY_FACTS_MAX,
    KEY_FACTS_MIN,
    KEY_FACTS_RATIO,
    MAX_KEY_FACTS_PER_COMPACT,
    REDACTED,
    KeyFact,
    KeyFactExtractor,
    build_extract_prompt,
    extract_with,
    key_fact_cap,
    looks_like_secret,
    parse_key_facts,
    redact_secrets,
    scrub_key_fact,
    slug_entity,
)
from .importance import build_score_prompt, score_with
from .protocol import IndexEntry, Layer, MemoryBackend, MemoryEntry, MemoryId
from .relevance import rank, recency_decay, relevance
from .store import ChainNode, ImportanceScorer, MemoryStore, RepairReport
from .summarize import MAX_SUMMARY_CHARS, Summarizer, SummaryPromoter, build_prompt, summarize_with
from .transcript import TranscriptStore

__all__ = [
    "Crystallizer",
    "FileBackend",
    "ImportanceScorer",
    "IndexEntry",
    "KEY_FACTS_MAX",
    "KEY_FACTS_MIN",
    "KEY_FACTS_RATIO",
    "KeyFact",
    "KeyFactExtractor",
    "Layer",
    "MAX_KEY_FACTS_PER_COMPACT",
    "MAX_SUMMARY_CHARS",
    "MemoryBackend",
    "MemoryEntry",
    "MemoryId",
    "MemoryStore",
    "PluginCandidate",
    "REDACTED",
    "ChainNode",
    "RepairReport",
    "Summarizer",
    "SummaryPromoter",
    "TranscriptStore",
    "batch_embed",
    "build_extract_prompt",
    "build_prompt",
    "build_score_prompt",
    "extract_with",
    "key_fact_cap",
    "looks_like_secret",
    "parse_key_facts",
    "redact_secrets",
    "rank",
    "recency_decay",
    "relevance",
    "score_with",
    "scrub_key_fact",
    "slug_entity",
    "summarize_with",
]
