"""文档化记忆数据模型：canonical Markdown 文档的渲染与解析。

一篇 note = 一个**自描述**的 canonical Markdown 文件：H1 标题 + 元数据行 +
头部 ``## Search Queries``（词法检索关键词）+ ``## Notes`` 正文。渲染
（:func:`render_note`）与解析（:func:`parse_note`）互为逆，格式定义**单一真源**于此。

对应规格：doc/openspec/specs/notes/spec.md
接口设计：doc/03-interfaces/notes-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass, field

_SEARCH_HEADER = "## Search Queries"
_NOTES_HEADER = "## Notes"
_TAG_SEP = ", "
_META_SEP = ": "


@dataclass
class NoteEntry:
    """一条文档化笔记（canonical Markdown 文件的领域模型）。"""

    note_id: str  # 主题标识（slug；即 canonical 文件名去扩展名）
    title: str = ""  # 人类可读标题（H1；空则回落 note_id）
    content: str = ""  # 正文（`## Notes` 之下）
    tags: list[str] = field(default_factory=list[str])
    source: str = "notes"
    updated_at: float = 0.0  # 秒级时间戳（覆盖式更新的「最新」判据）
    search_queries: list[str] = field(default_factory=list[str])  # 头部检索关键词（词法匹配）

    @property
    def path(self) -> str:
        """canonical 相对路径（派生自 note_id）。"""
        return f"{self.note_id}.md"


def slug_topic(text: str, *, max_len: int = 48) -> str:
    """任务 / 主题文本 → ``note_id`` slug。

    保留 ``str.isalnum()`` 字符（含 CJK），空白与标点折为单个 ``-``，去首尾 ``-`` 后截断。
    无可保留字符时返回空串（调用方据此跳过，不写盘）。
    """
    chars: list[str] = []
    prev_dash = False
    for ch in text.strip().lower():
        if ch.isalnum():
            chars.append(ch)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-")[:max_len].strip("-")


def render_note(note: NoteEntry) -> str:
    """``NoteEntry`` → canonical Markdown 全文（自描述）。"""
    queries = note.search_queries or _derive_queries(note)
    lines = [
        f"# {note.title or note.note_id}",
        "",
        f"- id{_META_SEP}{note.note_id}",
        f"- tags{_META_SEP}{_TAG_SEP.join(note.tags)}",
        f"- source{_META_SEP}{note.source}",
        f"- updated_at{_META_SEP}{note.updated_at}",
        "",
        _SEARCH_HEADER,
        "",
        *(f"- {q}" for q in queries),
        "",
        _NOTES_HEADER,
        "",
        note.content,
        "",
    ]
    return "\n".join(lines)


def parse_note(text: str, *, note_id: str | None = None, source: str = "notes") -> NoteEntry:
    """canonical Markdown 全文 → ``NoteEntry``（:func:`render_note` 的逆）。"""
    title = ""
    meta: dict[str, str] = {}
    queries: list[str] = []
    body: list[str] = []
    section = "head"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not title:
            title = stripped[2:].strip()
            continue
        if stripped == _SEARCH_HEADER:
            section = "queries"
            continue
        if stripped == _NOTES_HEADER:
            section = "body"
            continue
        if section == "head" and stripped.startswith("- ") and ":" in stripped:
            key, _, value = stripped[2:].partition(":")
            meta[key.strip()] = value.strip()
            continue
        if section == "queries" and stripped.startswith("- "):
            queries.append(stripped[2:].strip())
            continue
        if section == "body":
            body.append(line)
    return NoteEntry(
        note_id=note_id or meta.get("id") or slug_topic(title),
        title=title,
        content="\n".join(body).strip("\n"),
        tags=[tag for tag in (part.strip() for part in meta.get("tags", "").split(",")) if tag],
        source=meta.get("source") or source,
        updated_at=_to_float(meta.get("updated_at", "")),
        search_queries=queries,
    )


def _derive_queries(note: NoteEntry) -> list[str]:
    """缺省检索关键词：标题 + tags（去空）；全空时回落 note_id。"""
    candidates = [note.title, *note.tags] if note.title else list(note.tags)
    queries = [q for q in (item.strip() for item in candidates) if q]
    return queries or [note.note_id]


def _to_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0
