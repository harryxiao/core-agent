"""MarkdownBackend：以 canonical Markdown 文件为后端的 ``MemoryBackend`` 实现。

一篇 note = 一个 canonical Markdown 文件（:mod:`core.notes.models` 定义格式）。
实现既有 ``MemoryBackend`` Protocol 的 ``get/put/search/list_index/delete``（**签名不改**）：
``put`` 为**覆盖式**（同主题二次写 = 第二次内容，不拼接），先写临时文件再 ``os.replace``
（原子；替换前中断不留半截 canonical 文件）；``search`` 为**纯词法**（标题 / tags /
``## Search Queries`` / 正文；中文按 2-gram 切词）并对**语义浓缩字段分区加权**（只影响排序），
**不建向量库**。

``MemoryEntry.content`` = canonical 全文（自描述）⇒ ``get`` 用同一解析器还原 ``tags``/
``source``/``ts``，**不丢字段**。

对应规格：doc/openspec/specs/notes/spec.md
接口设计：doc/03-interfaces/notes-interface.md §2
"""

from __future__ import annotations

import os
from itertools import groupby
from pathlib import Path

from core.memory import IndexEntry, Layer, MemoryEntry, MemoryId

from .models import NoteEntry, parse_note

_SUFFIX = ".md"
_TMP_SUFFIX = ".md.tmp"
_NOTE_LAYER: Layer = "L2"
_CJK_START = "一"
_CJK_END = "鿿"
_TITLE_WEIGHT = 3  # 标题：语义浓缩最强
_META_WEIGHT = 2  # tags / `## Search Queries`：人工提炼的检索意图
_BODY_WEIGHT = 1  # note_id / 正文


def _is_cjk(char: str) -> bool:
    return _CJK_START <= char <= _CJK_END


def _segment(token: str) -> list[str]:
    """段内切词：CJK 连续段按 2-gram 展开（CJK 无词界），非 CJK 段整段保留。"""
    terms: list[str] = []
    for cjk, group in groupby(token, key=_is_cjk):
        text = "".join(group)
        if not text:
            continue
        if cjk and len(text) > 1:
            terms.extend(text[i : i + 2] for i in range(len(text) - 1))
        else:
            terms.append(text)
    return terms


def _terms(query: str) -> list[str]:
    """检索词：空白切分后逐段展开（中文任务句切成 2-gram，英文保持整词包含）。"""
    return [term for token in query.lower().split() for term in _segment(token)]


class MarkdownBackend:
    """``MemoryBackend`` Protocol 的文件系统实现（canonical Markdown 文件即真源）。"""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    # ---- MemoryBackend Protocol ----

    def get(self, layer: Layer, entry_id: MemoryId) -> MemoryEntry | None:
        found = self._read(self._path(entry_id))
        if found is None:
            return None
        note, raw = found
        return self._to_entry(layer, note, raw)

    def put(self, entry: MemoryEntry) -> MemoryId:
        # 覆盖式写入：canonical 文件逐字取自 entry.content（自描述全文），先 tmp 再 replace。
        self._write(entry.id, entry.content)
        return entry.id

    def search(self, query: str, layer: Layer | None = None) -> list[MemoryEntry]:
        terms = _terms(query)
        if not terms:
            return []
        hits = [
            (self._score(note, terms), self._to_entry(layer or _NOTE_LAYER, note, raw))
            for note, raw in self._entries()
        ]
        scored = [item for item in hits if item[0] > 0]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored]

    def list_index(self) -> IndexEntry:
        return IndexEntry([(note.note_id, _NOTE_LAYER) for note, _ in self._entries()])

    def delete(self, entry_id: MemoryId) -> None:
        self._path(entry_id).unlink(missing_ok=True)

    # ---- 内部辅助 ----

    def _path(self, entry_id: MemoryId) -> Path:
        # basename 归一：note_id 不含路径分隔符，避免越出 canonical 目录。
        return self._root / f"{os.path.basename(entry_id)}{_SUFFIX}"

    def _write(self, entry_id: MemoryId, text: str) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        target = self._path(entry_id)
        tmp = self._root / f"{os.path.basename(entry_id)}{_TMP_SUFFIX}"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)

    def _read(self, path: Path) -> tuple[NoteEntry, str] | None:
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8")
        return parse_note(raw, note_id=path.stem), raw

    def _entries(self) -> list[tuple[NoteEntry, str]]:
        if not self._root.is_dir():
            return []
        found: list[tuple[NoteEntry, str]] = []
        for path in sorted(self._root.glob(f"*{_SUFFIX}")):
            item = self._read(path)
            if item is not None:
                found.append(item)
        return found

    @staticmethod
    def _to_entry(layer: Layer, note: NoteEntry, raw: str) -> MemoryEntry:
        return MemoryEntry(
            id=note.note_id,
            layer=layer,
            content=raw,
            tags=list(note.tags),
            source=note.source,
            trace_id="notes",
            ts=note.updated_at,
            kind="semantic",
        )

    @staticmethod
    def _score(note: NoteEntry, terms: list[str]) -> float:
        """**分区加权**打分：语义浓缩字段（标题 / tags / ``## Search Queries``）权高于正文。

        命中判据仍是纯词法包含（CJK 2-gram 切词不变）；加权**只影响排序**——打分不再 ≤ 1，
        仅用于 ``> 0`` 过滤与降序排序、不外露。使**标题精确命中**的主题排在**仅正文顺带
        提及**的主题之前（change `0107`）。
        """
        weighted = (
            (note.title, _TITLE_WEIGHT),
            (" ".join(note.tags), _META_WEIGHT),
            (" ".join(note.search_queries), _META_WEIGHT),
            (note.note_id, _BODY_WEIGHT),
            (note.content, _BODY_WEIGHT),
        )
        score = sum(
            weight * sum(1 for term in terms if term in text.lower()) for text, weight in weighted
        )
        return score / len(terms)
