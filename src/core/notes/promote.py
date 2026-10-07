"""会话摘要提升（promotion）：``core.memory`` 会话摘要 → canonical note。

确定性、零 LLM 调用的提升工作流：由**调用方（CLI / 上层）显式触发**，把某会话的压实摘要
**覆盖式**落成一篇 canonical 常驻笔记（幂等：同会话重复提升命中同一 note、不增长）。
复用 ``NoteStore.update()``（**唯一**写路径）；依赖方向 ``notes → core.memory`` 已存在
（见 ``notes/store.py``）⇒ **不新增**反向依赖。

对应规格：doc/openspec/specs/notes/spec.md「会话摘要提升（promotion）」
change 0150 / ADR-0142 / 账本 E94。
"""

from __future__ import annotations

from core.memory import MemoryEntry

from .errors import NoteError
from .models import NoteEntry, slug_topic
from .store import NoteStore

_PROMOTE_PREFIX = "session-"
_PROMOTE_SOURCE = "notes.promote"


def promote_session_summary(  # noqa: PLR0913 — 注入面皆可选（as_note_id/title/pin）
    store: NoteStore,
    summary: MemoryEntry,
    *,
    session_id: str,
    as_note_id: str | None = None,
    title: str = "",
    pin: bool = True,
) -> NoteEntry | None:
    """把一条会话摘要提升为 canonical 常驻笔记（幂等覆盖）。

    ``note_id`` 由 ``session_id`` 确定性派生（``session-<slug>``），可由 ``as_note_id`` 覆盖；
    派生结果为空且未给显式 id ⇒ 返回 ``None``（**不写盘**，与 ``observe_turn`` 同口径守卫）。
    产出置 ``pinned=pin``（缺省 ``True``：每轮无条件注入）。写入**不**接 ``EffectTracker``
    （承文档层既有取舍）。

    ``pin=False`` 供**半自动路径**（memory 压实侧首次越界时经提升钩子交付；change 0153 /
    路线图 G3）：产出为**普通** canonical 笔记（只经 Consult 命中面与 digest 注入），**不**自动置
    常驻、**不**占常驻预算。显式路径（CLI）用缺省 ``True``，逐字不变。

    **来源守护**（change 0151）：目标 ``note_id`` 撞上来源**非** ``notes.promote`` 的既有笔记、
    且调用方**未**显式给出 ``as_note_id`` ⇒ 返回 ``None``（**不写盘**，绝不覆写外来源正文）。
    显式 ``as_note_id`` ⇒ 视为**显式授权**，照常覆写（不受守护约束）。
    """
    derived = slug_topic(session_id)
    if as_note_id is None and not derived:
        return None
    note_id = as_note_id or f"{_PROMOTE_PREFIX}{derived}"

    try:
        existing: NoteEntry | None = store.get(note_id)
    except NoteError:
        existing = None

    if existing is not None and existing.source != _PROMOTE_SOURCE and as_note_id is None:
        return None

    body = f"## 会话摘要（提升自会话 {session_id}）\n\n{summary.content.strip()}"
    resolved_title = (
        title or (existing.title if existing is not None else "") or f"会话摘要 {session_id}"
    )
    tags = ["promotion", f"session:{session_id}", "summary"]
    if existing is not None:
        tags.extend(tag for tag in existing.tags if tag not in tags)

    return store.update(
        NoteEntry(
            note_id=note_id,
            title=resolved_title,
            content=body,
            tags=tags,
            source=_PROMOTE_SOURCE,
            pinned=pin,
        )
    )
