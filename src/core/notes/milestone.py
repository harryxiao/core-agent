"""里程碑报告锚定（milestone anchoring）：阶段收口 → 结构化 canonical 常驻笔记。

**确定性、零 LLM 调用**（PA-08 方案 B）：由调用方（CLI / 上层）显式触发，把结论 / 关键决策 /
硬约束 / 关键事实装配成一篇笔记并置常驻（``pinned=True`` + 高 ``pin_priority``）。复用既有
「常驻（pinned）笔记」注入通道 —— **不新增**注入块、不改 loop / prompt 装配。

正文固定节次序：结论 → 关键决策 → 硬约束 → 关键事实；空节整节省略。所有内容先经
``redact_secrets``（密钥红线），装配后正文有界（``MAX_MILESTONE_CHARS``，保留头部 + 可见截断标记）。
复用 ``NoteStore.update()``（**唯一**写路径），写入**不**接 ``EffectTracker``（承文档层既有取舍）。

对应规格：doc/openspec/specs/notes/spec.md「里程碑报告锚定（milestone anchoring）」
change 0273 / ADR-0263 / 账本 E209。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from core.memory import MemoryEntry, redact_secrets

from .errors import NoteError
from .models import NoteEntry, slug_topic
from .store import NoteStore

MILESTONE_SOURCE = "notes.milestone"
MILESTONE_PIN_PRIORITY = 100  # 高于人工 `notes pin` 的缺省 0：阶段硬约束优先在场
MAX_MILESTONE_CHARS = 3000  # < 常驻总预算 4000：给同场其它常驻笔记留余量

_MILESTONE_PREFIX = "milestone-"


def _clean(items: Iterable[str]) -> list[str]:
    """去空白、丢空条目；保持调用方给定次序。"""
    cleaned = [text.strip() for text in items]
    return [text for text in cleaned if text]


def _section(title: str, blocks: Sequence[str]) -> str:
    """一节 = 标题 + 空行 + 条目（空节返回空串）。"""
    if not blocks:
        return ""
    return f"{title}\n\n" + "\n\n".join(blocks)


def _assemble(
    *,
    summary_text: str,
    conclusions: Sequence[str],
    decisions: Sequence[str],
    constraints: Sequence[str],
    facts: Sequence[MemoryEntry],
) -> str:
    """按固定节次序装配正文（不脱敏、不截断 —— 由调用方统一收口）。"""
    conclusion_blocks = [summary_text] if summary_text else []
    conclusion_blocks += [f"- {text}" for text in conclusions]
    fact_lines = sorted(
        (f"- {entry.content.strip()}" for entry in facts if entry.content.strip()),
    )
    sections = (
        _section("## 结论", conclusion_blocks),
        _section("## 关键决策", [f"- {text}" for text in decisions]),
        _section("## 硬约束", [f"- {text}" for text in constraints]),
        _section("## 关键事实", fact_lines),
    )
    return "\n\n".join(section for section in sections if section)


def _bound(text: str) -> str:
    """正文上界：保留头部 + 含被截字符数的标记；总长 ≤ ``MAX_MILESTONE_CHARS``。"""
    if len(text) <= MAX_MILESTONE_CHARS:
        return text
    keep = MAX_MILESTONE_CHARS
    while True:
        suffix = f"\n…[truncated {len(text) - keep} chars]…"
        new_keep = MAX_MILESTONE_CHARS - len(suffix)
        if new_keep == keep:
            return text[:new_keep] + suffix
        keep = new_keep


def close_milestone(  # noqa: PLR0913 — 输入面皆可选（summary/key_facts/as_note_id/title/priority）
    store: NoteStore,
    *,
    milestone: str,
    session_id: str = "",
    summary: MemoryEntry | None = None,
    key_facts: Iterable[MemoryEntry] = (),
    conclusions: Sequence[str] = (),
    decisions: Sequence[str] = (),
    constraints: Sequence[str] = (),
    as_note_id: str | None = None,
    title: str = "",
    priority: int = MILESTONE_PIN_PRIORITY,
) -> NoteEntry | None:
    """把一次阶段收口装配为 canonical 常驻笔记（幂等覆盖；无内容 ⇒ ``None``，不写盘）。

    ``note_id`` 由里程碑名确定性派生（``milestone-<slug>``），可由 ``as_note_id`` 覆盖；
    派生 id 为空且未给显式 id ⇒ ``None``。**来源守护**：目标撞上来源非 ``notes.milestone``
    的既有笔记且未给 ``as_note_id`` ⇒ ``None``（绝不覆写外来源正文）；显式 id 视为授权。
    """
    derived = slug_topic(milestone)
    if as_note_id is None and not derived:
        return None
    note_id = as_note_id or f"{_MILESTONE_PREFIX}{derived}"

    body = _assemble(
        summary_text=summary.content.strip() if summary is not None else "",
        conclusions=_clean(conclusions),
        decisions=_clean(decisions),
        constraints=_clean(constraints),
        facts=list(key_facts),
    )
    if not body:
        return None

    try:
        existing: NoteEntry | None = store.get(note_id)
    except NoteError:
        existing = None
    if existing is not None and existing.source != MILESTONE_SOURCE and as_note_id is None:
        return None

    resolved_title = (
        title or (existing.title if existing is not None else "") or f"里程碑 {milestone.strip()}"
    )
    slug = derived or slug_topic(note_id)
    tags = ["milestone", f"milestone:{slug}", "anchor"]
    if session_id:
        tags.append(f"session:{session_id}")
    if existing is not None:
        tags.extend(tag for tag in existing.tags if tag not in tags)

    return store.update(
        NoteEntry(
            note_id=note_id,
            title=redact_secrets(resolved_title),
            content=_bound(redact_secrets(body)),
            tags=tags,
            source=MILESTONE_SOURCE,
            pinned=True,
            pin_priority=priority,
        )
    )
