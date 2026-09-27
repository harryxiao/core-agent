"""信息地图（InfoMap / 二级索引）。

把长文档转为轻量目录索引（章节/要点/位置指针），模型先定位指针再按需
取片段，不把全文塞入窗口；源文档变更（hash 不一致）时增量重建，重建失败
降级为对原始文档的受控分段线性扫描。

对应接口：doc/03-interfaces/context-interface.md §3
"""

from __future__ import annotations

import hashlib

from .errors import ContextError, ContextErrorCode
from .models import MapEntry, Pointer

_HEADING_PREFIX = "#"


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _terms(query: str) -> list[str]:
    return [t for t in query.lower().split() if t]


def _match(pointer: Pointer, terms: list[str]) -> bool:
    haystack = f"{pointer.section} {pointer.summary}".lower()
    return any(t in haystack for t in terms)


class InfoMap:
    """信息地图：文档 → 目录索引，支持失效重建与线性扫描兜底。"""

    def __init__(self) -> None:
        self._docs: dict[str, str] = {}  # 原始文档（重建/兜底用）
        self._maps: dict[str, MapEntry] = {}  # doc_id → 目录索引

    def index(self, doc_id: str, content: str) -> MapEntry:
        """把长文档转为目录索引（章节/要点/位置指针），并缓存原文。"""
        self._docs[doc_id] = content
        entry = MapEntry(
            doc_id=doc_id,
            content_hash=_hash(content),
            pointers=self._build_pointers(doc_id, content),
        )
        self._maps[doc_id] = entry
        return entry

    def lookup(self, doc_id: str, query: str) -> list[Pointer]:
        """按查询定位相关指针；地图缺失时对原文做受控线性扫描兜底。"""
        entry = self._maps.get(doc_id)
        if entry is None:
            return self._linear_scan(doc_id, query)
        terms = _terms(query)
        if not terms:
            return list(entry.pointers)
        return [p for p in entry.pointers if _match(p, terms)]

    def rebuild_if_stale(self, doc_id: str, content_hash: str) -> None:
        """源文档 hash 与索引不一致时增量重建；无法重建抛 MAP_STALE。"""
        entry = self._maps.get(doc_id)
        if entry is None:
            raise ContextError(ContextErrorCode.MAP_STALE, f"信息地图缺失: {doc_id}")
        if entry.content_hash == content_hash:
            return
        raw = self._docs.get(doc_id)
        if raw is None:
            raise ContextError(ContextErrorCode.MAP_STALE, f"信息地图失效且无法重建: {doc_id}")
        self.index(doc_id, raw)

    # ---- 内部辅助 ----

    def _build_pointers(self, doc_id: str, content: str) -> list[Pointer]:
        pointers: list[Pointer] = []
        offset = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(_HEADING_PREFIX):
                section = stripped.lstrip(_HEADING_PREFIX).strip()
                pointers.append(
                    Pointer(doc_id=doc_id, section=section, summary=section, offset=offset)
                )
            offset += len(line) + 1
        if not pointers:
            pointers.append(Pointer(doc_id=doc_id, section=doc_id, summary=content[:80], offset=0))
        return pointers

    def _linear_scan(self, doc_id: str, query: str) -> list[Pointer]:
        raw = self._docs.get(doc_id)
        if raw is None:
            return []
        terms = _terms(query)
        pointers: list[Pointer] = []
        for i, line in enumerate(raw.splitlines()):
            if terms and not any(t in line.lower() for t in terms):
                continue
            pointers.append(Pointer(doc_id=doc_id, section=f"seg-{i}", summary=line[:80], offset=i))
        return pointers
