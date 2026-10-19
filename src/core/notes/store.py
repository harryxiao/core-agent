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
import warnings
from collections.abc import Callable
from pathlib import Path

from core.memory import Layer, MemoryEntry, redact_secrets
from core.plugin_registry import Plugin

from .backend import MarkdownBackend
from .errors import NoteError, NoteErrorCode
from .models import NoteEntry, parse_note, render_note, slug_topic

_NOTE_LAYER: Layer = "L2"
_TURN_SOURCE = "notes.turn"  # 逐轮写回（observe_turn）产出的来源标记（来源守护判据）
_MAX_EXCERPT_CHARS = 200
_MAX_DIGEST_CHARS = 1200
_MAX_PINNED_CHARS = 4000  # 常驻注入总量上界（独立于 digest 的 1200；有界 ⇒ token 有界）

# 效应闸门（change 0176 / ADR-0167）：只有产生**持久化效应**的轮次才值得沉淀。
# 内置工具 id 形如 ``tools.<名>``（`_action_steps` 行首即完整 tool_id）；工具名从行首解析。
_TOOL_ID_PREFIX = "tools."
_WRITE_EFFECT_TOOLS = frozenset(
    {
        "file_write",  # 文件系统写
        "file_patch",
        "code_run",  # 代码执行（产生副作用；失败见 _ERROR_MARKER）
        "gate_run",  # 质量门禁（产出验证结论）
        "install",  # 插件注册表效应
        "uninstall",
    }
)
_ERROR_MARKER = "错误："  # `loop._summarize_result` 对失败观察渲染的前缀

# 提升产物的来源标记（唯一真源：`notes/promote.py` 写入、本模块据此识别归档来源）。
PROMOTE_SOURCE = "notes.promote"

# 归档来源排除面（change 0180 / ADR-0171）：正文**源自 memory 会话摘要**的留档物 ——
# 该摘要已由 loop「历史摘要（长期）」块每轮注入 ⇒ 其**节选** SHALL NOT 再进 Consult 命中面
# （同源内容免二次注入）。只约束 `digest` 注入面：
# `consult`/`search`/`list`/`pinned_digest` 口径逐字不变。
_ARCHIVE_SOURCES = frozenset({PROMOTE_SOURCE})


def _tool_of_step(step: str) -> str:
    """行动序列行 → 工具名（行首至首个 ``（``）；非该形态 ⇒ 整行（⇒ 匹配不到已知工具名）。"""
    return step.split("（", 1)[0].strip()


def has_write_effect(steps: list[str]) -> bool:
    """本轮是否含**成功的写效应**工具动作（确定性、零 LLM —— 与 ADR-0045 依赖方向一致）。

    纯读型动作（``file_read`` / ``web_fetch`` / ``context_read`` / ``list``）产出的内容是
    **素材**，归 memory 侧 keyfact 抽取路径沉淀，不进 canonical notes（刻意知识层）；
    写效应动作**失败**（行含 `错误：`）亦不计 —— 只沉淀**验证过的**行动与结果。
    """
    for step in steps:
        tool = _tool_of_step(step).removeprefix(_TOOL_ID_PREFIX)
        if tool in _WRITE_EFFECT_TOOLS and _ERROR_MARKER not in step:
            return True
    return False


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

    def raw(self, note_id: str) -> str | None:
        """读一篇 canonical 的**原始字节**（回收/备份用）；不存在返回 ``None``。

        与 ``get()`` 的差别：不解析、不重建 —— 回收目录要求「逐字可恢复」。
        """
        entry = self._backend.get(_NOTE_LAYER, note_id)
        return entry.content if entry is not None else None

    def remove(self, note_id: str) -> None:
        """删除一篇 canonical（仅限显式运维入口，如 ``notes prune``）。

        不存在 → ``NOTE_NOT_FOUND``。
        """
        if self._load(note_id) is None:
            raise NoteError(NoteErrorCode.NOTE_NOT_FOUND, f"笔记不存在: {note_id}")
        self._backend.delete(note_id)

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
        """确定性摘要：命中笔记节选 + 笔记清单（供 loop 注入，**不自动全量注入正文**）。

        命中节选 SHALL 排除**归档来源**笔记（``_ARCHIVE_SOURCES``，如提升产物）：其正文源自 memory
        会话摘要、已由 loop「历史摘要（长期）」块每轮注入 ⇒ 此处不再重复；此类笔记仍以**清单标题**
        在场（存在性可见）。``consult`` / ``search`` / ``list`` 的检索语义不受此排除影响。
        """
        sections: list[str] = []
        hits = [note for note in self.consult(query) if note.source not in _ARCHIVE_SOURCES]
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

    def pinned(self) -> list[NoteEntry]:
        """常驻（pinned）笔记清单：**优先级降序**、同优先级按 ``note_id`` 升序 —— **确定性**。

        「谁在场」由**显式优先级**（操作者的决定，change 0154）而非 ``note_id`` 字典序决定。
        """
        return sorted(
            (note for note in self.list() if note.pinned),
            key=lambda note: (-note.pin_priority, note.note_id),
        )

    def pinned_digest(self) -> str:
        """常驻注入块：常驻笔记**完整正文**（每轮无条件注入；与 ``digest`` 的命中面**互不交叉**）。

        无 query 入参（无条件），故与 Consult 是两条独立通道；空正文的常驻笔记**不占块**
        （避免每轮出现一个只说标题、不说约束的空块）；总长有界 ⇒ token 有界（P5）。
        块内**不含** ``updated_at``：块字节只随正文变，跨轮稳定。

        **整篇纳入**（change 0154）：一篇要么**整篇**在场、要么**整篇**不在场，**绝不半篇**
        （半截硬约束可能语义反转，比缺席更危险）。超预算篇**整篇排除**且其后各篇不挤入
        （在场集合是优先级次序的**前缀**）；唯一例外是次序**首篇**自身超限时仍整篇纳入
        （块不因单篇超限而空 —— 硬约束全灭更糟）。超预算时经 ``warnings.warn`` 留痕。
        """
        block, excluded = self._assemble_pinned()
        if excluded or len(block) > _MAX_PINNED_CHARS:
            warnings.warn(
                f"pinned notes exceed the injection budget ({_MAX_PINNED_CHARS} chars); "
                f"block={len(block)}; not injected: {', '.join(excluded) or '<none: single note>'}"
                " — set notes with `notes pin --priority` to choose who stays in context",
                RuntimeWarning,
                stacklevel=2,
            )
        return block

    def pinned_overflow(self) -> list[str]:
        """因常驻预算超限而**未进场**的常驻笔记 ``note_id``（次序同 ``pinned()``）。

        只读、无副作用；单篇超限的**首篇**不在其列（它整篇在场）。
        """
        return self._assemble_pinned()[1]

    def set_pinned(self, note_id: str, *, pinned: bool = True, priority: int = 0) -> NoteEntry:
        """置 / 清常驻标记并设定优先级；缺失 ⇒ ``NOTE_NOT_FOUND``。

        **幂等**：``pinned`` 与 ``priority`` **皆未变化** ⇒ 直接返回、**不写盘、不 bump**
        ``updated_at`` —— 反复 ``pin`` 不得搅动 canonical 文件的时间戳（否则「最新即权威」判据
        被无意义写入污染）。真变更走 ``update()``（**唯一**写回路径），不另开第二写路径。

        **清常驻**（``pinned=False``）同时把 ``priority`` 归零 —— 退出常驻面即不再有优先级。
        """
        note = self.get(note_id)
        new_priority = priority if pinned else 0
        if note.pinned == pinned and note.pin_priority == new_priority:
            return note
        note.pinned = pinned
        note.pin_priority = new_priority
        return self.update(note)

    def observe_turn(self, task: str, steps: list[str], *, ok: bool) -> NoteEntry | None:
        """任务后 Update：成功轮把「解决过程」覆盖式写回任务主题；不适用则返回 ``None``。

        **来源守护**（change 0151）：一条主题只应由**产生它的那条写路径**覆写。若任务主题
        （``slug_topic(task)``）撞上来源**非** ``notes.turn`` 的既有笔记（人工撰写 / promotion
        产出 / 其他路径），则**不改写**该主题 —— 本轮沉淀改写入首个不冲突的派生主题
        ``"<topic>-<n>"``（既保外来源正文逐字不变，也不丢本轮沉淀）。来源为 ``notes.turn``
        （或主题不存在）时保持既有覆盖式写回，**逐字不变**。

        **有意义闸门**（change 0171）：``steps`` 为空（纯文字回复轮 —— 无任何工具行动）⇒
        **不落盘**（返回 ``None``），与 ``ok=False`` / 空 slug 同口径 —— 琐碎轮不得创建或覆写
        canonical 文件。正文的可读渲染（非 ReAct 原文）由 loop 侧 ``_action_steps`` 保证。

        **效应闸门**（change 0176 / ADR-0167）：``steps`` 非空但**不含任何成功的写效应工具动作**
        （仅纯读型动作，或写效应动作失败）⇒ 同样**不落盘** —— 纯读产出的内容是**素材**（归 memory
        侧 keyfact 抽取），不进 canonical 知识层。判据确定性（按行首工具名匹配写效应工具集），
        非工具行形态 ⇒ 保守判定为无写效应。
        """
        if not ok or not steps or not has_write_effect(steps):
            return None
        topic = slug_topic(task)
        if not topic:
            return None
        # 脱敏在**有界截断之前**（change 0254）：命中密钥形态的子串替换为 `<redacted>`，
        # 工具名 / 路径与动作结构保留 —— 「做了什么」仍是可读信息。
        body = "## 解决过程\n" + "\n".join(f"- {redact_secrets(step)}" for step in steps)
        title = task.strip().splitlines()[0] if task.strip() else topic

        existing = self._load(topic)
        if existing is not None and existing.source != _TURN_SOURCE:
            topic = self._derived_turn_topic(topic)
            existing = self._load(topic)
        return self.update(
            NoteEntry(
                note_id=topic,
                title=title,
                content=body,
                tags=list(existing.tags) if existing is not None else [],
                # 逐轮写回不得抹除常驻标记与优先级
                pinned=existing.pinned if existing is not None else False,
                pin_priority=existing.pin_priority if existing is not None else 0,
                source=_TURN_SOURCE,
            )
        )

    def _derived_turn_topic(self, base: str) -> str:
        """来源守护下的派生主题：首个「不存在、或来源为 ``notes.turn``」的 ``"<base>-<n>"``（n≥2）。

        外来源笔记占据 ``base`` 时，逐轮沉淀改道 ``base-2``…；同一派生主题后续轮次**复用**（覆盖式
        写回），故不无谓增长。
        """
        n = 2
        while True:
            candidate = f"{base}-{n}"
            entry = self._load(candidate)
            if entry is None or entry.source == _TURN_SOURCE:
                return candidate
            n += 1

    # ---- 内部辅助 ----

    def _assemble_pinned(self) -> tuple[str, list[str]]:
        """按 ``pinned()`` 次序**整篇纳入**，返回 ``(注入块, 未进场 note_id 列表)``。

        次序首篇**无条件**纳入（即便自身超预算 —— 块不因单篇超限而空）；此后任一篇整篇放不下即
        **整篇排除**，且其后各篇一律不再尝试（在场集合是优先级次序的**前缀**，低优先级不得越过
        被排除者挤入）。空正文的常驻笔记**预先滤除**：既不占块、也不计未进场。
        """
        included: list[str] = []
        excluded: list[str] = []
        total = 0
        for note in self.pinned():
            if not note.content.strip():
                continue
            section = f"## {note.title or note.note_id}（{note.note_id}）\n{note.content.strip()}"
            addition = len(section) + (2 if included else 0)  # 篇间 "\n\n" 分隔
            # 一旦有篇被排除，其后各篇一律不再尝试（低优先级不越位挤入 —— 前缀语义）
            if excluded or (included and total + addition > _MAX_PINNED_CHARS):
                excluded.append(note.note_id)
                continue
            included.append(section)
            total += addition
        return "\n\n".join(included), excluded

    def _load(self, note_id: str, *, layer: Layer = _NOTE_LAYER) -> NoteEntry | None:
        entry = self._backend.get(layer, note_id)
        if entry is None:
            return None
        return parse_note(entry.content, note_id=note_id, source=entry.source)


def _excerpt(note: NoteEntry) -> str:
    text = " ".join(note.content.split())
    return text[:_MAX_EXCERPT_CHARS]
