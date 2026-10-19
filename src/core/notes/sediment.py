"""沉淀候选区：成功轮 → 结构化候选 → 显式晋升（change 0295）。

两段式沉淀的 L2 侧实现：

- **预滤**（确定性、零模型调用）：只让「成功、有写效应、非短指令」的轮次进入提炼；
- **提炼**（DI 可调用，notes 不 import 任何 LLM 抽象）：严格 JSON 产出结构化候选，
  解析失败/非持久一律丢弃（fail-closed）；
- **候选区**：独立 JSON，不进入 ``digest`` / ``list`` / ``search``，未晋升内容不污染上下文；
- **晋升**：``NoteStore.update()`` 是唯一 canonical 写路径，``source=notes.sediment``，
  来源守护 + ``sediment:<candidate>`` 标签防候选互相覆盖。

对应规格：doc/openspec/specs/notes/spec.md（沉淀候选区与晋升）
"""

from __future__ import annotations

import json
import os
import threading
import time
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from hashlib import blake2b
from pathlib import Path
from typing import Protocol, cast

from core.memory import redact_secrets

from ._private import write_private_json
from .errors import NoteError, NoteErrorCode
from .models import NoteEntry, slug_topic
from .store import has_write_effect

# 提炼器契约：prompt → 文本（同 ``SopWriter`` 的 DI 方向；组合根注入模型调用）
CandidateWriter = Callable[[str], str]

# 晋升产物的来源标记（与 notes.turn / notes.promote / notes.rag 并列）
SEDIMENT_SOURCE = "notes.sediment"

CANDIDATE_LIMIT = 128
AUTO_PROMOTE_MIN_SUPPORT = 2

_MIN_TASK_CHARS = 6
_MAX_TASK_CHARS = 500
_MAX_STEP_CHARS = 300
_MAX_STEPS = 20
_MAX_REPLY_CHARS = 1500
_MAX_TITLE_CHARS = 120
_MAX_CONTENT_CHARS = 4000
_MAX_TAGS = 8
_MAX_TAG_CHARS = 40
_MAX_QUERIES = 8
_MAX_QUERY_CHARS = 80
_MAX_EVIDENCE_CHARS = 120
_MAX_TRACE_DIGESTS = 8
_MAX_KNOWN_TOPICS = 40
_KINDS = frozenset({"decision", "procedure", "fact", "preference", "pitfall"})

_PROMPT_HEAD = (
    "你是记忆沉淀器。判断本轮任务是否产生了**值得长期保留、将来会再次用到**的知识，"
    "并把它整理为一篇结构化笔记。不要记录一次性的任务细节、寒暄、操作流水或没有结论的尝试。"
    "只输出一个 JSON 对象，字段：\n"
    '{"durable": true/false, "topic": "短横线小写英文或拼音 slug", '
    '"title": "人类可读标题", "content": "Markdown 正文（结论/步骤/依据）", '
    '"tags": ["..."], "queries": ["将来检索会用到的关键词"], '
    '"kind": "decision|procedure|fact|preference|pitfall"}\n'
    '没有可复用知识时输出 {"durable": false}。正文不得复述对话原文或整段工具输出。'
)


def _default_candidates_path() -> Path:
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / "notes-candidates.json"


def _clip(text: str, limit: int) -> str:
    return text[:limit]


def _as_str_list(value: object, *, limit: int, item_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [_clip(item, item_limit) for item in items[:limit] if isinstance(item, str) and item]


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return default
    try:
        return float(value)
    except ValueError:
        return default


class _NoteSink(Protocol):
    """沉淀只依赖 NoteStore 的 get/update/list 三枚方法（不 import loop/skills）。"""

    def get(self, note_id: str) -> NoteEntry: ...

    def update(self, note: NoteEntry) -> NoteEntry: ...

    def list(self) -> list[NoteEntry]: ...


@dataclass
class Candidate:
    """候选区条目：结构化笔记 + 支持度/证据。"""

    candidate_id: str
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list[str])
    queries: list[str] = field(default_factory=list[str])
    kind: str = "fact"
    support: int = 1
    first_seen: float = 0.0
    last_seen: float = 0.0
    trace_digests: list[str] = field(default_factory=list[str])
    evidence: str = ""


class CandidateStore:
    """候选区 JSON 存储：0600、原子写、有界、损坏容忍、进程内串行化。"""

    def __init__(
        self,
        path: Path | None = None,
        *,
        limit: int = CANDIDATE_LIMIT,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._path = Path(path) if path is not None else _default_candidates_path()
        self._limit = limit
        self._clock = clock if clock is not None else time.time
        self._lock = threading.RLock()
        self._candidates: dict[str, Candidate] = {}
        self._load()

    def list(self) -> list[Candidate]:
        with self._lock:
            return sorted(
                self._candidates.values(),
                key=lambda item: (-item.last_seen, item.candidate_id),
            )

    def get(self, candidate_id: str) -> Candidate:
        with self._lock:
            return self._candidates[candidate_id]

    def upsert(self, candidate: Candidate, *, trace_digest: str = "") -> Candidate:
        """按 ``candidate_id`` 合并；``trace_digest`` 未见过才 +1 支持度。"""
        with self._lock:
            now = self._clock()
            existing = self._candidates.get(candidate.candidate_id)
            if existing is None:
                candidate.first_seen = now
                candidate.last_seen = now
                candidate.support = 1
                candidate.trace_digests = [trace_digest] if trace_digest else []
                merged = candidate
            else:
                existing.title = candidate.title
                existing.content = candidate.content
                existing.tags = list(candidate.tags)
                existing.queries = list(candidate.queries)
                existing.kind = candidate.kind
                existing.evidence = candidate.evidence
                existing.last_seen = now
                if trace_digest and trace_digest not in existing.trace_digests:
                    existing.support += 1
                    existing.trace_digests = (existing.trace_digests + [trace_digest])[
                        -_MAX_TRACE_DIGESTS:
                    ]
                merged = existing
            self._candidates[merged.candidate_id] = merged
            self._evict()
            self._persist()
            return merged

    def remove(self, candidate_id: str) -> bool:
        with self._lock:
            removed = self._candidates.pop(candidate_id, None) is not None
            if removed:
                self._persist()
            return removed

    # ---- 落盘 ----

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            parsed = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            self._load_corrupt()
            return
        if not isinstance(parsed, dict):
            self._load_corrupt()
            return
        raw = cast("dict[str, object]", parsed)
        loaded: dict[str, Candidate] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                self._load_corrupt()
                return
            data = cast("dict[str, object]", value)
            candidate_id = str(data.get("candidate_id") or key)
            loaded[candidate_id] = Candidate(
                candidate_id=candidate_id,
                title=str(data.get("title") or ""),
                content=str(data.get("content") or ""),
                tags=_as_str_list(data.get("tags"), limit=_MAX_TAGS, item_limit=_MAX_TAG_CHARS),
                queries=_as_str_list(
                    data.get("queries"), limit=_MAX_QUERIES, item_limit=_MAX_QUERY_CHARS
                ),
                kind=str(data.get("kind") or "fact"),
                support=_as_int(data.get("support"), 1),
                first_seen=_as_float(data.get("first_seen"), 0.0),
                last_seen=_as_float(data.get("last_seen"), 0.0),
                trace_digests=_as_str_list(
                    data.get("trace_digests"), limit=_MAX_TRACE_DIGESTS, item_limit=64
                ),
                evidence=str(data.get("evidence") or ""),
            )
        self._candidates = loaded

    def _load_corrupt(self) -> None:
        warnings.warn(
            "候选区不可读，按空态启动（不加载任何候选）",
            stacklevel=2,
        )
        self._candidates = {}

    def _persist(self) -> None:
        payload = {key: asdict(value) for key, value in self._candidates.items()}
        write_private_json(self._path, payload)

    def _evict(self) -> None:
        while len(self._candidates) > self._limit:
            oldest = min(
                self._candidates.values(),
                key=lambda item: (item.last_seen, item.first_seen, item.candidate_id),
            )
            del self._candidates[oldest.candidate_id]


class Sedimenter:
    """两段式沉淀：预滤 → 候选；显式晋升后才写 canonical。"""

    def __init__(  # noqa: PLR0913 — 构造注入面（提炼器 + 落盘 + 时钟 + 自动晋升）
        self,
        note_store: _NoteSink,
        *,
        writer: CandidateWriter | None = None,
        path: Path | None = None,
        store: CandidateStore | None = None,
        clock: Callable[[], float] | None = None,
        auto_promote: bool = False,
        min_support: int = AUTO_PROMOTE_MIN_SUPPORT,
    ) -> None:
        # 只依赖 NoteStore 的 get/update 两枚方法（便于测试替身）；不 import loop/skills。
        self._notes = note_store
        self._writer = writer
        self._clock = clock if clock is not None else time.time
        self._store = store if store is not None else CandidateStore(path, clock=self._clock)
        self._auto_promote = auto_promote
        self._min_support = min_support
        self._lock = threading.RLock()

    # ---- 观察面 ----

    def observe_turn(
        self, task: str, steps: list[str], *, ok: bool, reply: str = ""
    ) -> Candidate | None:
        """成功轮 → 候选；预滤不通过/提炼失败/非持久 ⇒ ``None`` 且零落盘。"""
        if not ok or self._writer is None or not steps or not has_write_effect(steps):
            return None
        if len("".join(task.split())) < _MIN_TASK_CHARS:
            return None

        prompt = self._build_prompt(task, steps, reply)
        try:
            text = self._writer(prompt)
        except Exception:  # noqa: BLE001 — 提炼失败不中断主流程
            warnings.warn("沉淀提炼失败，本轮不产候选", stacklevel=2)
            return None
        candidate = self._parse(text, task)
        if candidate is None:
            return None

        trace_digest = blake2b("\n".join(steps).encode("utf-8"), digest_size=8).hexdigest()
        with self._lock:
            merged = self._store.upsert(candidate, trace_digest=trace_digest)
            if self._auto_promote and merged.support >= self._min_support:
                try:
                    self.promote(merged.candidate_id)
                except (NoteError, KeyError):
                    warnings.warn(
                        f"候选自动晋升被拒，保留候选（{merged.candidate_id}）",
                        stacklevel=2,
                    )
            return merged

    # ---- 候选运维 ----

    def list_candidates(self) -> list[Candidate]:
        return self._store.list()

    def get_candidate(self, candidate_id: str) -> Candidate:
        return self._store.get(candidate_id)

    def reject(self, candidate_id: str) -> bool:
        return self._store.remove(candidate_id)

    def promote(
        self, candidate_id: str, *, as_topic: str | None = None, title: str = ""
    ) -> NoteEntry:
        """显式晋升：候选 → canonical（来源守护；成功后移除候选）。"""
        with self._lock:
            candidate = self._store.get(candidate_id)
            topic = slug_topic(as_topic or candidate.candidate_id)
            if not topic:
                raise ValueError("晋升目标主题为空")

            existing = self._existing(topic)
            if existing is not None:
                if existing.source != SEDIMENT_SOURCE:
                    raise NoteError(
                        NoteErrorCode.TOPIC_EXISTS,
                        f"主题已存在且来源为 {existing.source}: {topic}（可用 --as 指定新主题）",
                    )
                own_tag = f"sediment:{candidate_id}"
                foreign = [
                    tag for tag in existing.tags if tag.startswith("sediment:") and tag != own_tag
                ]
                if foreign:
                    raise NoteError(
                        NoteErrorCode.TOPIC_EXISTS,
                        f"主题已由其他候选晋升: {topic}（{foreign[0]}）",
                    )

            own_tag = f"sediment:{candidate_id}"
            tags = list(existing.tags) if existing is not None else []
            tags = [tag for tag in tags if tag != own_tag]
            for tag in candidate.tags:
                if tag not in tags:
                    tags.append(tag)
            tags.append(own_tag)

            note = NoteEntry(
                note_id=topic,
                title=_clip(title or candidate.title or topic, _MAX_TITLE_CHARS),
                content=candidate.content,
                tags=tags,
                search_queries=list(candidate.queries),
                pinned=existing.pinned if existing is not None else False,
                pin_priority=existing.pin_priority if existing is not None else 0,
                source=SEDIMENT_SOURCE,
            )
            self._notes.update(note)
            self._store.remove(candidate_id)
            return note

    # ---- 内部辅助 ----

    def _existing(self, topic: str) -> NoteEntry | None:
        try:
            return self._notes.get(topic)
        except NoteError:
            return None

    def _build_prompt(self, task: str, steps: list[str], reply: str) -> str:
        known = [item.candidate_id for item in self._store.list()[:_MAX_KNOWN_TOPICS]]
        known.extend(note.note_id for note in self._notes.list()[:_MAX_KNOWN_TOPICS])
        known_text = ", ".join(dict.fromkeys(known)) or "（无）"
        blocks = [
            _PROMPT_HEAD,
            "",
            f"任务：{redact_secrets(_clip(task, _MAX_TASK_CHARS))}",
            "",
            "执行轨迹：",
            *[f"- {redact_secrets(_clip(step, _MAX_STEP_CHARS))}" for step in steps[:_MAX_STEPS]],
            "",
            f"最终回复：{redact_secrets(_clip(reply, _MAX_REPLY_CHARS))}",
            "",
            f"已有主题（可复用则沿用其 id）：{known_text}",
        ]
        return "\n".join(blocks)

    @staticmethod
    def _parse(text: str, task: str) -> Candidate | None:  # noqa: PLR0911 — fail-closed 早退
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except (TypeError, ValueError):
            return None
        if not isinstance(parsed, dict):
            return None
        data = cast("dict[str, object]", parsed)
        if data.get("durable") is not True:
            return None
        topic_raw = data.get("topic")
        if not isinstance(topic_raw, str):
            return None
        topic = slug_topic(topic_raw)
        content = data.get("content")
        if not topic or not isinstance(content, str) or not content.strip():
            return None
        kind = str(data.get("kind") or "fact")
        if kind not in _KINDS:
            kind = "fact"
        title = data.get("title")
        return Candidate(
            candidate_id=topic,
            title=_clip(title, _MAX_TITLE_CHARS) if isinstance(title, str) and title else topic,
            content=_clip(content, _MAX_CONTENT_CHARS),
            tags=_as_str_list(data.get("tags"), limit=_MAX_TAGS, item_limit=_MAX_TAG_CHARS),
            queries=_as_str_list(
                data.get("queries"), limit=_MAX_QUERIES, item_limit=_MAX_QUERY_CHARS
            ),
            kind=kind,
            evidence=_clip(
                task.strip().splitlines()[0] if task.strip() else "", _MAX_EVIDENCE_CHARS
            ),
        )


def candidate_writer_with(llm: Callable[[str], str]) -> CandidateWriter:
    """把「prompt → 文本」的模型调用适配为 ``Sedimenter`` 的提炼契约。"""

    def _write(prompt: str) -> str:
        return llm(prompt).strip()

    return _write
