"""具体记忆存储（memory）。

实现 Plugin 四要素 + MemoryStore 契约：分层写入（无行动证据拒绝）、
热/冷检索（失败降级不抛）、相关性排序 + 预算截断、层间迁移、可逆写入。

对应接口：doc/03-interfaces/memory-interface.md §1
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict

from core.judgment import Compactor, DecisionResult
from core.plugin_registry import Effect, EffectTracker

from .backend import FileBackend
from .protocol import IndexEntry, Layer, MemoryBackend, MemoryEntry, MemoryId
from .relevance import rank

# 粗略 token 估算：约 4 字符 ≈ 1 token（read 预算截断用）
_TOKEN_DIVISOR = 4

# 向量缓存上界（超出按 FIFO 逐出）；进程内易失，不落盘
_VEC_CACHE_MAX = 4096


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
        compactor: Compactor | None = None,
    ) -> None:
        self._backend = backend if backend is not None else FileBackend()
        self._tracker = effect_tracker if effect_tracker is not None else EffectTracker()
        self._embedder = embedder
        self._compactor = compactor
        self._hot: dict[str, MemoryEntry] = {}
        self._vectors: dict[str, list[float]] = {}
        self._embed_failed = False

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
        embedder = self._memo_embedder() if self._embedder is not None else None
        ranked = sorted(
            candidates.values(),
            key=lambda e: rank(e, query, embedder),
            reverse=True,
        )
        selected = self._truncate(ranked, budget)
        for entry in selected:
            entry.reuse_count += 1  # 复用即强化（进程内强化，不落盘避免写放大）
        return selected

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

    def compact(self, query: str = "", budget: int = 4096) -> DecisionResult | None:
        """以 score 原语压实：注入 Compactor 时评分保留/丢弃，未注入返回 None。"""
        if self._compactor is None:
            return None
        items = self.read(query, budget=budget)
        return self._compactor.score(
            {"query": query, "count": len(items)},
            [asdict(entry) for entry in items],
        )

    # ---- 内部辅助 ----

    def _memo_embedder(self) -> Callable[[list[str]], list[list[float]]]:
        """批量 embedder 的**文本级向量缓存**包装：命中即复用，未变内容零重算。

        每次 ``read`` 对 query 至多向量化一次；条目内容未变则复用缓存向量。首次调用
        失败即置 ``_embed_failed`` 短路（后续直接抛、不再触网），交由 ``relevance`` 的
        词法降级兜底。
        """

        def _embed(texts: list[str]) -> list[list[float]]:
            if self._embed_failed:
                raise RuntimeError("embedder unavailable")  # noqa: TRY003 — 触发词法降级
            keys = [hashlib.blake2b(t.encode("utf-8"), digest_size=16).hexdigest() for t in texts]
            out: list[list[float]] = [self._vectors.get(k, []) for k in keys]
            missing = [
                (i, k, t)
                for i, (k, t) in enumerate(zip(keys, texts, strict=True))
                if k not in self._vectors
            ]
            if missing:
                try:
                    vecs = self._embedder([t for _, _, t in missing])  # type: ignore[misc]
                except Exception:
                    self._embed_failed = True
                    raise
                for (i, k, _), vec in zip(missing, vecs, strict=True):
                    self._vectors[k] = vec
                    out[i] = vec
                self._trim_vectors()
            return out

        return _embed

    def _trim_vectors(self) -> None:
        while len(self._vectors) > _VEC_CACHE_MAX:
            self._vectors.pop(next(iter(self._vectors)))

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
