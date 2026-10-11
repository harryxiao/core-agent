"""可插拔记忆后端（memory）。

MVP 实现 FileBackend：JSONL 落盘 + 内存热字典。get / put / search /
list_index / delete 五入口；``path`` 为空则纯内存（测试友好、无磁盘副作用）。

对应接口：doc/03-interfaces/memory-interface.md §5
"""

from __future__ import annotations

import json
import os
import threading
import warnings
from dataclasses import asdict
from pathlib import Path

from .protocol import IndexEntry, Layer, MemoryEntry, MemoryId
from .relevance import tokens


class FileBackend:
    """文件后端：JSONL 落盘 + 内存热字典。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._entries: dict[str, MemoryEntry] = {}
        self._index: list[tuple[str, Layer]] = []
        self._lock = threading.RLock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                self._load()

    def get(self, layer: Layer, entry_id: MemoryId) -> MemoryEntry | None:
        entry = self._entries.get(entry_id)
        return entry if entry is not None and entry.layer == layer else None

    def put(self, entry: MemoryEntry) -> MemoryId:
        with self._lock:
            self._entries[entry.id] = entry
            self._index = [(i, layer) for i, layer in self._index if i != entry.id]
            self._index.append((entry.id, entry.layer))
            self._persist()
        return entry.id

    def search(self, query: str, layer: Layer | None = None) -> list[MemoryEntry]:
        # 候选集按层过滤；query 词元与 content/tags 重叠打分后降序返回
        with self._lock:
            candidates = [e for e in self._entries.values() if layer is None or e.layer == layer]
            if not query:
                return candidates
            query_tokens = tokens(query)
            scored: list[tuple[int, MemoryEntry]] = []
            for entry in candidates:
                haystack = f"{entry.content} {' '.join(entry.tags)}".lower()
                score = sum(1 for tok in query_tokens if tok in haystack)
                scored.append((score, entry))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            return [entry for _, entry in scored]

    def list_index(self) -> IndexEntry:
        with self._lock:
            return IndexEntry(entries=list(self._index))

    def delete(self, entry_id: MemoryId) -> None:
        with self._lock:
            self._entries.pop(entry_id, None)
            self._index = [(i, layer) for i, layer in self._index if i != entry_id]
            self._persist()

    def _load(self) -> None:
        path = self._path
        if path is None:
            return
        # 逐行容错（change 0206 / 台账 E143）：半行（ValueError）与结构不符行（TypeError）
        # 跳过并汇总告警——损坏的记忆文件 SHALL NOT 阻断启动（与 CheckpointStore 同口径）。
        # 告警只报计数与文件名，不回显行内容（条目可能含敏感信息）。
        bad = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = MemoryEntry(**json.loads(line))
            except (ValueError, TypeError):
                bad += 1
                continue
            self._entries[entry.id] = entry
            self._index.append((entry.id, entry.layer))
        if bad:
            warnings.warn(f"记忆落盘含 {bad} 条损坏行，已跳过: {path.name}", stacklevel=2)

    def _persist(self) -> None:
        path = self._path
        if path is None:
            return
        # 原子提交（change 0206 / 台账 E143）：tmp + os.replace——写中途被杀不损坏既有集合
        # （镜像 persistence.write_state 的写法；JSONL 是拼接串，不复用其 json.dumps 本体）。
        lines = [json.dumps(asdict(e), ensure_ascii=False) + "\n" for e in self._entries.values()]
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text("".join(lines), encoding="utf-8")
        os.replace(tmp, path)
