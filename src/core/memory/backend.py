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
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from core.filelock import exclusive_file_lock

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
            self._persist({entry.id: entry}, ())
        return entry.id

    def put_many(self, entries: Sequence[MemoryEntry]) -> None:
        """批量写回：一次更新内存集与索引，**单次落盘**（change 0244）。

        复用强化一次检索命中多条时，逐条 ``put`` 会触发 N 次全量 JSONL 重写；批量入口把
        N 次重写降为 1 次。语义与逐条 ``put`` 相同（同 id 覆盖、索引去重后追加）。
        """
        with self._lock:
            ids = {entry.id for entry in entries}
            self._entries.update({entry.id: entry for entry in entries})
            self._index = [(i, layer) for i, layer in self._index if i not in ids]
            self._index.extend((entry.id, entry.layer) for entry in entries)
            self._persist({entry.id: entry for entry in entries}, ())

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
            self._persist({}, (entry_id,))

    def _load(self) -> None:
        path = self._path
        if path is None:
            return
        self._entries = self._read_entries(path, warn=True)
        self._index = [(entry.id, entry.layer) for entry in self._entries.values()]

    @staticmethod
    def _read_entries(path: Path, *, warn: bool) -> dict[str, MemoryEntry]:
        """逐行解析落盘文件（change 0206 容错口径；change 0301 起落盘合并复用）。

        半行（ValueError）与结构不符行（TypeError）跳过——损坏的记忆文件 SHALL NOT 阻断
        启动（与 CheckpointStore 同口径）。``warn`` 只在启动加载时为真：落盘合并路径读到
        坏行是常态（另一进程半写会由原子替换挡住），不反复告警。
        告警只报计数与文件名，不回显行内容（条目可能含敏感信息）。
        """
        entries: dict[str, MemoryEntry] = {}
        bad = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = MemoryEntry(**json.loads(line))
            except (ValueError, TypeError):
                bad += 1
                continue
            entries[entry.id] = entry
        if bad and warn:
            warnings.warn(f"记忆落盘含 {bad} 条损坏行，已跳过: {path.name}", stacklevel=2)
        return entries

    def _persist(self, changed: Mapping[str, MemoryEntry], deleted: Sequence[MemoryId]) -> None:
        """变更集合并落盘（change 0301）：锁内读盘 → 覆盖/删除本次变更 → 原子写。

        旧实现用**进程启动时的内存快照**整体重写 —— TUI / `task` / cron 共用同一
        ``memory.jsonl`` 时会静默覆盖对方的写入。现在基线是**盘上最新集合**，同一 id 的
        竞争保持 last-writer-wins；删除只移除指定 id（不复活他进程已删条目）。锁为
        fail-open 短建议锁（``exclusive_file_lock``）：锁不可用则退化为无锁写，记忆写入
        SHALL NOT 成为新的失败面。落盘成功后进程内集合采纳合并结果（他进程写入可见）。
        """
        path = self._path
        if path is None:
            return
        with exclusive_file_lock(path):
            merged = self._read_entries(path, warn=False) if path.exists() else {}
            merged.update(changed)
            for entry_id in deleted:
                merged.pop(entry_id, None)
            # 原子提交（change 0206 / 台账 E143）：tmp + os.replace——写中途被杀不损坏既有集合
            # （镜像 persistence.write_state 的写法；JSONL 是拼接串，不复用其 json.dumps 本体）。
            lines = [json.dumps(asdict(e), ensure_ascii=False) + "\n" for e in merged.values()]
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text("".join(lines), encoding="utf-8")
            os.replace(tmp, path)
            self._entries = merged
            self._index = [(entry.id, entry.layer) for entry in merged.values()]
