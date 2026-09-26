"""具体记忆存储（memory）。

实现 Plugin 四要素 + MemoryStore 契约：分层写入（无行动证据拒绝）、
热/冷检索（失败降级不抛）、相关性排序 + 预算截断、层间迁移、可逆写入。

对应接口：doc/03-interfaces/memory-interface.md §1
"""

from __future__ import annotations

import time
from collections.abc import Callable

from core.plugin_registry import Effect, EffectTracker

from .backend import FileBackend
from .protocol import IndexEntry, Layer, MemoryBackend, MemoryEntry, MemoryId
from .relevance import relevance

# 粗略 token 估算：约 4 字符 ≈ 1 token（read 预算截断用）
_TOKEN_DIVISOR = 4


class MemoryStore:
    """具体记忆存储：内存热字典 + 可插拔后端（MVP 为 FileBackend）。"""

    plugin_id = "memory.store"
    generation = 1
    schema: dict[str, object] = {"type": "object"}
    coeffects: list[str] = []

    def __init__(
        self,
        backend: MemoryBackend | None = None,
        effect_tracker: EffectTracker | None = None,
        embedder: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        self._backend = backend if backend is not None else FileBackend()
        self._tracker = effect_tracker if effect_tracker is not None else EffectTracker()
        self._embedder = embedder
        self._hot: dict[str, MemoryEntry] = {}

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True

    def read(self, query: str, budget: int = 4096) -> list[MemoryEntry]:
        try:
            cold = self._backend.search(query)
        except Exception:  # noqa: BLE001 — 冷区检索失败降级
            cold = []
        candidates = {entry.id: entry for entry in cold}
        candidates.update(self._hot)
        ranked = sorted(
            candidates.values(),
            key=lambda e: relevance(e, query, self._embedder),
            reverse=True,
        )
        return self._truncate(ranked, budget)

    def write(self, layer: Layer, entry: MemoryEntry) -> MemoryId | None:
        if not entry.source or not entry.trace_id:
            return None  # 无行动不记忆
        entry.layer = layer
        if entry.ts <= 0:
            entry.ts = time.time()
        self._backend.put(entry)
        self._hot[entry.id] = entry
        self._tracker.record(
            Effect(
                op="memory.write",
                target=entry.id,
                undo=lambda: self._undo_write(entry.id),
                reversible=True,
                coeffect=[],
                trace_id=entry.trace_id,
                ts=time.time(),
            )
        )
        return entry.id

    def migrate(self, entry_id: MemoryId, src: Layer, dst: Layer) -> None:
        entry = self._backend.get(src, entry_id)
        if entry is None:
            entry = self._hot.get(entry_id)
        if entry is None or entry.layer != src:
            return
        entry.layer = dst
        self._backend.put(entry)
        self._hot[entry.id] = entry

    def index(self) -> IndexEntry:
        return self._backend.list_index()

    def audit(self, trace_id: str | None = None) -> list[MemoryEntry]:
        entries = self._backend.search("")
        if trace_id is None:
            return entries
        return [e for e in entries if e.trace_id == trace_id]

    # ---- 内部辅助 ----

    def _truncate(self, entries: list[MemoryEntry], budget: int) -> list[MemoryEntry]:
        selected: list[MemoryEntry] = []
        used = 0
        for entry in entries:
            cost = max(1, len(entry.content) // _TOKEN_DIVISOR)
            if selected and used + cost > budget:
                break
            selected.append(entry)
            used += cost
        return selected

    def _undo_write(self, entry_id: str) -> None:
        self._hot.pop(entry_id, None)
        self._backend.delete(entry_id)
