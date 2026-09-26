"""记忆系统（L2，能力可调）。

L0-L4 分层记忆、热/冷温度检索、无行动不记忆、结晶/溶解、可逆写入；
``MemoryStore`` / ``Crystallizer`` 为具体类（实现 Plugin 契约），
``MemoryBackend`` 保持 Protocol（可插拔后端）。

对应规格：doc/openspec/specs/memory/spec.md
"""

from .backend import FileBackend
from .crystallizer import Crystallizer, PluginCandidate
from .protocol import IndexEntry, Layer, MemoryBackend, MemoryEntry, MemoryId
from .relevance import relevance
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
    "relevance",
]
