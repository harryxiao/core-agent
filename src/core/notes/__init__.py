"""文档化记忆（notes）：canonical Markdown 真相层 + Consult→Build→Update 循环。

与既有 RAG 语义召回层（``core.memory``）**并列互补**：RAG 负责语义召回，notes 负责权威真相。
**不引入 RAG / embedding / 向量库**。``MarkdownBackend`` 实现既有 ``MemoryBackend`` Protocol
（只实现、不修改契约）；内置循环技能 ``skills.notes.consult_build_update`` 由组合根构造并
经 ``SkillLibrary`` 触达（本包**不依赖** ``core.skills``，保持 L2 真相层不向上依赖）。

对应规格：doc/openspec/specs/notes/spec.md
接口设计：doc/03-interfaces/notes-interface.md
"""

from .backend import MarkdownBackend
from .errors import NoteError, NoteErrorCode
from .milestone import (
    MAX_MILESTONE_CHARS,
    MILESTONE_PIN_PRIORITY,
    MILESTONE_SOURCE,
    close_milestone,
)
from .models import NoteEntry, parse_note, render_note, slug_topic
from .promote import promote_session_summary
from .store import NoteStore

__all__ = [
    "MAX_MILESTONE_CHARS",
    "MILESTONE_PIN_PRIORITY",
    "MILESTONE_SOURCE",
    "MarkdownBackend",
    "NoteEntry",
    "NoteError",
    "NoteErrorCode",
    "NoteStore",
    "close_milestone",
    "parse_note",
    "promote_session_summary",
    "render_note",
    "slug_topic",
]
