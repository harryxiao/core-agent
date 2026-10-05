"""NoteStore：文档化真相层的存储门面（Plugin）。

收口 canonical Markdown 真相层的读写面，并承载 Consult→Build→Update 循环的两处接缝：
``digest``（任务前确定性读取命中笔记 + 清单，供 loop 注入）与 ``observe_turn``（成功轮把
新结论覆盖式写回）。后端经 ``MemoryBackend`` Protocol 复用（缺省 ``MarkdownBackend``）。

对应规格：doc/openspec/specs/notes/spec.md
接口设计：doc/03-interfaces/notes-interface.md §3
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from core.memory import Layer, MemoryEntry
from core.plugin_registry import Plugin

from .backend import MarkdownBackend
from .errors import NoteError, NoteErrorCode
from .models import NoteEntry, parse_note, render_note, slug_topic

_NOTE_LAYER: Layer = "L2"
_MAX_EXCERPT_CHARS = 200
_MAX_DIGEST_CHARS = 1200


def _default_root() -> Path:
    """canonical 目录缺省位置：$CORE_STATE_DIR（缺省 ~/.core/state）/notes。"""
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "notes"


class NoteStore(Plugin):
    """文档化记忆存储门面：canonical Markdown 真相层的读写 + 循环纪律接缝。"""

    plugin_id = "notes.store"
    generation = 1
    schema: dict[str, object] = {"type": "object"}
    coeffects = ["filesystem:write"]

    def __init__(
        self,
        backend: MarkdownBackend | None = None,
        *,
        path: Path | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._backend = backend if backend is not None else MarkdownBackend(path or _default_root())
        self._clock = clock if clock is not None else time.time

    # ---- Plugin 生命周期 ----

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True

    # ---- 读写面 ----

    def get(self, note_id: str) -> NoteEntry:
        """读一篇 canonical 笔记；不存在 → ``NOTE_NOT_FOUND``。"""
        note = self._load(note_id)
        if note is None:
            raise NoteError(NoteErrorCode.NOTE_NOT_FOUND, f"笔记不存在: {note_id}")
        return note

    def create(
        self,
        note_id: str,
        *,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
    ) -> NoteEntry:
        """显式创建主题；已存在 → ``TOPIC_EXISTS``（不覆盖既有内容）。"""
        if self._load(note_id) is not None:
            raise NoteError(NoteErrorCode.TOPIC_EXISTS, f"主题已存在: {note_id}")
        return self.update(
            NoteEntry(note_id=note_id, title=title, content=content, tags=list(tags or []))
        )

    def ensure(
        self,
        note_id: str,
        *,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
    ) -> NoteEntry:
        """幂等 get-or-create（已存在直接返回，不报 ``TOPIC_EXISTS``）。"""
        existing = self._load(note_id)
        if existing is not None:
            return existing
        return self.create(note_id, title=title, content=content, tags=tags)

    def update(self, note: NoteEntry) -> NoteEntry:
        """upsert：以 ``note`` 覆盖式写回对应主题（最新最权威），时间戳取当前。"""
        note.updated_at = self._clock()
        self._backend.put(
            MemoryEntry(
                id=note.note_id,
                layer=_NOTE_LAYER,
                content=render_note(note),
                tags=list(note.tags),
                source=note.source,
                trace_id="notes",
                ts=note.updated_at,
            )
        )
        return note

    def list(self) -> list[NoteEntry]:
        """canonical 文件清单（标题 / id / 更新时间）。"""
        notes: list[NoteEntry] = []
        for note_id, layer in self._backend.list_index().entries:
            loaded = self._load(note_id, layer=layer)
            if loaded is not None:
                notes.append(loaded)
        return notes

    def search(self, query: str, *, top_k: int = 5) -> list[NoteEntry]:
        """纯词法检索（标题 / tags / ``## Search Queries`` / 正文），得分降序取 top-k。"""
        hits = self._backend.search(query)
        return [parse_note(entry.content, note_id=entry.id) for entry in hits[:top_k]]

    def consult(self, query: str, *, top_k: int = 3) -> list[NoteEntry]:
        """任务前 Consult：读与任务相关的 canonical 笔记（词法命中）。"""
        return self.search(query, top_k=top_k)

    # ---- 循环纪律接缝 ----

    def digest(self, query: str) -> str:
        """确定性摘要：命中笔记节选 + 笔记清单（供 loop 注入，**不自动全量注入正文**）。"""
        sections: list[str] = []
        hits = self.consult(query)
        if hits:
            sections.append(
                "命中的笔记：\n"
                + "\n".join(
                    f"- {note.title or note.note_id}（{note.note_id}）：{_excerpt(note)}"
                    for note in hits
                )
            )
        catalog = self.list()
        if catalog:
            sections.append(
                "笔记清单：\n"
                + "\n".join(f"- {note.title or note.note_id} [{note.note_id}]" for note in catalog)
            )
        return "\n\n".join(sections)[:_MAX_DIGEST_CHARS]

    def observe_turn(self, task: str, steps: list[str], *, ok: bool) -> NoteEntry | None:
        """任务后 Update：成功轮把「解决过程」覆盖式写回任务主题；不适用则返回 ``None``。"""
        if not ok:
            return None
        topic = slug_topic(task)
        if not topic:
            return None
        body = "## 解决过程\n" + "\n".join(f"- {step}" for step in steps)
        title = task.strip().splitlines()[0] if task.strip() else topic
        existing = self._load(topic)
        return self.update(
            NoteEntry(
                note_id=topic,
                title=title,
                content=body,
                tags=list(existing.tags) if existing is not None else [],
                source="notes.turn",
            )
        )

    # ---- 内部辅助 ----

    def _load(self, note_id: str, *, layer: Layer = _NOTE_LAYER) -> NoteEntry | None:
        entry = self._backend.get(layer, note_id)
        if entry is None:
            return None
        return parse_note(entry.content, note_id=note_id, source=entry.source)


def _excerpt(note: NoteEntry) -> str:
    text = " ".join(note.content.split())
    return text[:_MAX_EXCERPT_CHARS]
