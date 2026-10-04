"""记忆系统（L2，能力可调）。

L0-L4 分层记忆、热/冷温度检索、无行动不记忆、结晶/溶解、可逆写入；
``MemoryStore`` / ``Crystallizer`` 为具体类（实现 Plugin 契约），
``MemoryBackend`` 保持 Protocol（可插拔后端）。

对应规格：doc/openspec/specs/memory/spec.md
"""

from .backend import FileBackend
from .crystallizer import Crystallizer, PluginCandidate
from .embedding import batch_embed
from .protocol import IndexEntry, Layer, MemoryBackend, MemoryEntry, MemoryId
from .relevance import rank, recency_decay, relevance
from .store import MemoryStore

__all__ = [
    "Crystallizer",
    "FileBackend",
    "IndexEntry",
    "Layer",
    "MemoryBackend",
    "MemoryEntry",
    "MemoryId",
    "MemoryStore",
    "PluginCandidate",
    "batch_embed",
    "rank",
    "recency_decay",
    "relevance",
]
