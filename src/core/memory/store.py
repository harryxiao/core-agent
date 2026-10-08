"""具体记忆存储（memory）。

实现 Plugin 四要素 + MemoryStore 契约：分层写入（无行动证据拒绝）、
热/冷检索（失败降级不抛）、相关性排序 + 预算截断、层间迁移、可逆写入。

对应接口：doc/03-interfaces/memory-interface.md §1
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import warnings
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.judgment import Compactor, DecisionResult
from core.plugin_registry import Effect, EffectTracker

from .backend import FileBackend
from .extract import (
    MAX_KEY_FACTS_PER_COMPACT,
    REDACTED,
    KeyFact,
    KeyFactExtractor,
    scrub_key_fact,
    slug_entity,
)
from .protocol import IndexEntry, Layer, MemoryBackend, MemoryEntry, MemoryId
from .relevance import rank, recency_decay
from .summarize import MAX_SUMMARY_CHARS, Summarizer, SummaryPromoter

# 粗略 token 估算：约 4 字符 ≈ 1 token（read 预算截断用）
_TOKEN_DIVISOR = 4

# 向量缓存上界（超出按 FIFO 逐出）；进程内易失，不落盘
_VEC_CACHE_MAX = 4096

# 价值门控阈值：会话内最高分低于此值则不提炼（仅本轮取得分值时才设门槛）
_CONSOLIDATE_THRESHOLD = 0.5

# 遗忘阈值：衰减评分低于此值即归档（≈19 天零复用零重要度）
_FORGET_THRESHOLD = 0.05

# 单次压实的逐条目打分调用上界（score 原语一次只给一条目的分）
_MAX_SCORED_PER_COMPACT = 20

# 关键事实条目标签前缀（`MAX_KEY_FACTS_PER_COMPACT` 见 extract 模块）
_KEY_FACT_TAG = "key_fact"

# 出处（引用）标签前缀；`coeffect:` 形态的取值才是可用引用（change 0173 / ADR-0164）
_REF_TAG = "ref:"
_COEFFECT_REF_PREFIX = "coeffect:"

# 会话溯源标签前缀（`_write_key_fact` 在会话非空时追加）
_SESSION_TAG = "session:"


def _repair_backup_path(stamp: str | None = None) -> Path:
    """修复操作的备份文件路径：$CORE_STATE_DIR（缺省 ~/.core/state）/memory.repair.<时间戳>.jsonl。

    与 `memory.jsonl` 同目录、同格式（每行一条 `MemoryEntry`）—— 该文件是修复删除的**持久**
    可逆性来源。
    """
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / f"memory.repair.{stamp or time.strftime('%Y%m%d-%H%M%S')}.jsonl"


@dataclass
class RepairReport:
    """一次失效关键事实修复的结果（报表口径见 design §D5）。"""

    identified: list[str] = field(default_factory=list[str])  # 识别到的失效条目 id
    sessions: list[str] = field(default_factory=list[str])  # 涉及的会话（可重抽的单位）
    deleted: list[str] = field(default_factory=list[str])  # 实际删除的条目 id
    written: list[str] = field(default_factory=list[str])  # 重抽落库的条目 id
    backup_path: str = ""  # 备份文件路径（未落备份则空串）
    skipped: dict[str, list[str]] = field(default_factory=dict[str, list[str]])  # 原因 → 目标
    dry_run: bool = False


def _decay_score(entry: MemoryEntry) -> float:
    """遗忘评分：新鲜度 × 复用频次 × 重要度（三者皆低才归档）。"""
    return recency_decay(entry) * (1.0 + math.log1p(entry.reuse_count)) * (1.0 + entry.importance)


def _below_gate(entries: list[MemoryEntry], scores: dict[str, float]) -> bool:
    """价值门控：条目中**取得本轮分值**者最高分低于阈值即跳过该会话。

    一个分值都没取得（未注入 scorer / 打分失败 / 超出打分上界）时**不设门槛**——与
    「未注入 scorer 不设门槛」同一取向，避免决策服务抖动导致记忆停止固化。
    """
    got = [scores[entry.id] for entry in entries if entry.id in scores]
    return bool(got) and max(got) < _CONSOLIDATE_THRESHOLD


def _plan_key_facts(raw: list[KeyFact]) -> tuple[list[KeyFact], list[str], list[str]]:
    """整批归一化关键事实：**脱敏 + 同批归并 + 有界**。

    返回（可落库事实, 因密钥丢弃的实体名, 因同批同 slug 被归并的实体名）。

    脱敏由 ``scrub_key_fact`` 无条件执行（注入方不构成信任边界）；无实体 slug 者不计入落库。
    **同批**内 slug 相同者只留**首条**（change 0172）—— 同批重复是**单次模型响应内的重复枚举**，
    区别于跨压实的「重复抽取」（后者由同实体幂等覆盖处理，`_write_key_fact` 同一 `id`）。
    归并后条数计额 ⇒ 重复项不再挤占 `MAX_KEY_FACTS_PER_COMPACT`。
    """
    plan: list[KeyFact] = []
    dropped: list[str] = []
    deduped: list[str] = []
    seen: set[str] = set()
    for fact in raw:
        cleaned = scrub_key_fact(fact)
        if cleaned is None:
            dropped.append(fact.entity.strip() or "<?>")
            continue
        slug = slug_entity(cleaned.entity)
        if not slug:
            continue
        if slug in seen:
            deduped.append(cleaned.entity.strip())
            continue
        seen.add(slug)
        plan.append(cleaned)
        if len(plan) >= MAX_KEY_FACTS_PER_COMPACT:
            break
    return plan, dropped, deduped


class MemoryStore:
    """具体记忆存储：内存热字典 + 可插拔后端（MVP 为 FileBackend）。"""

    plugin_id = "memory.store"
    generation = 1
    schema: dict[str, object] = {"type": "object"}
    coeffects: list[str] = []

    def __init__(  # noqa: PLR0913, PLR0917 — 注入面均为可选依赖注入
        self,
        backend: MemoryBackend | None = None,
        effect_tracker: EffectTracker | None = None,
        embedder: Callable[[list[str]], list[list[float]]] | None = None,
        compactor: Compactor | None = None,
        summarizer: Summarizer | None = None,
        summary_promoter: SummaryPromoter | None = None,
        key_fact_extractor: KeyFactExtractor | None = None,
    ) -> None:
        self._backend = backend if backend is not None else FileBackend()
        self._tracker = effect_tracker if effect_tracker is not None else EffectTracker()
        self._embedder = embedder
        self._compactor = compactor
        self._summarizer = summarizer
        self._summary_promoter = summary_promoter
        self._key_fact_extractor = key_fact_extractor
        self._hot: dict[str, MemoryEntry] = {}
        self._vectors: dict[str, list[float]] = {}
        self._embed_failed = False

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True

    def read(
        self,
        query: str,
        budget: int = 4096,
        *,
        exclude_source_prefixes: tuple[str, ...] = (),
        allow_source_prefixes: tuple[str, ...] = (),
        session_id: str = "",
    ) -> list[MemoryEntry]:
        """检索相关记忆；``exclude_source_prefixes`` 命中的来源在**排名与预算之前**剔除
        （被排除项不吃预算、不被复用计数强化）。缺省空元组 ⇒ 检索语义与既往逐字一致。

        ``allow_source_prefixes`` 是排除面的**例外面**：同时命中排除前缀与放行前缀的条目**放行**
        （「排除某类来源，但放行其中指定前缀」——神兽读自身 ``beast.<agent_id>`` 即此用例）。
        排除面为空时放行面不产生任何效果（无排除即无所放行）。

        ``session_id`` 非空时**只**返回归属该会话的条目 + **全局层**（未归属 ``""``）条目；
        会话过滤与来源排除同一位置（排名与预算之前），故被滤项同样不吃预算、不被强化。
        缺省空串 = 未归属调用者 ⇒ 不过滤（与既往语义逐字一致）。
        """
        try:
            cold = self._backend.search(query)
        except Exception:  # noqa: BLE001 — 冷区检索失败降级
            cold = []
        candidates = {entry.id: entry for entry in cold}
        candidates.update(self._hot)
        if exclude_source_prefixes:
            candidates = {
                entry_id: entry
                for entry_id, entry in candidates.items()
                if not (
                    entry.source.startswith(exclude_source_prefixes)
                    and not entry.source.startswith(allow_source_prefixes)
                )
            }
        if session_id:
            candidates = {
                entry_id: entry
                for entry_id, entry in candidates.items()
                if entry.session_id in ("", session_id)
            }
        embedder = self._memo_embedder() if self._embedder is not None else None
        ranked = sorted(
            candidates.values(),
            key=lambda e: rank(e, query, embedder),
            reverse=True,
        )
        selected = self._truncate(ranked, budget)
        for entry in selected:
            entry.reuse_count += 1  # 复用即强化（进程内强化，不落盘避免写放大）
        return selected

    def write(self, layer: Layer, entry: MemoryEntry) -> MemoryId | None:
        if not entry.source or not entry.trace_id:
            return None  # 无行动不记忆
        entry.layer = layer
        if entry.ts <= 0:
            entry.ts = time.time()
        self._backend.put(entry)
        self._hot[entry.id] = entry
        self._tracker.record(
            Effect(
                op="memory.write",
                target=entry.id,
                undo=lambda: self._undo_write(entry.id),
                reversible=True,
                coeffect=[],
                trace_id=entry.trace_id,
                ts=time.time(),
            )
        )
        return entry.id

    def migrate(
        self, entry_id: MemoryId, src: Layer, dst: Layer, *, trace_id: str | None = None
    ) -> None:
        """层间迁移（可撤销）：记录 ``Effect``，按 ``trace_id`` 回滚即迁回原层。

        ``trace_id`` 缺省取条目自身来源 trace；压实等批量操作传入统一 trace，
        使摘要写入与整批迁移可一起撤销。
        """
        entry = self._backend.get(src, entry_id)
        if entry is None:
            entry = self._hot.get(entry_id)
        if entry is None or entry.layer != src:
            return
        entry.layer = dst
        self._backend.put(entry)
        self._hot[entry.id] = entry
        self._tracker.record(
            Effect(
                op="memory.migrate",
                target=entry_id,
                undo=lambda: self._undo_migrate(entry_id, dst, src),
                reversible=True,
                coeffect=[],
                trace_id=trace_id or entry.trace_id,
                ts=time.time(),
            )
        )

    def index(self) -> IndexEntry:
        return self._backend.list_index()

    def audit(self, trace_id: str | None = None) -> list[MemoryEntry]:
        entries = self._backend.search("")
        if trace_id is None:
            return entries
        return [e for e in entries if e.trace_id == trace_id]

    def summary_for(self, session_id: str) -> MemoryEntry | None:
        """按会话取回既有摘要条目（**只读**；口径同 `_commit_summary`；无则 ``None``）。

        复用私有 `_existing_summary` ⇒ id 约定单一真源、零写入 / 零效应、
        不变更 `reuse_count` / `importance` / `updated_at`。供上层（如 CLI 提升）取数。
        """
        return self._existing_summary(session_id)

    def compact(
        self, query: str = "", budget: int = 4096, *, session_id: str = ""
    ) -> DecisionResult | None:
        """压实记忆：score 原语评分决策 + 注入摘要器时的会话摘要提炼（0041）。

        未注入 ``summarizer`` 时**只评分不写**（降级：不写摘要、不动原条目）；注入时按
        ``session_id`` 聚合 L2 episodic 条目，提炼为一条 semantic 摘要条目并**归档**原条目
        （迁 L4，不删除），全部效应按 ``trace_id=f"compaction.<session_id>"`` 可撤销。
        摘要提炼异常不吞：向上传播，由触发点记录并重试（原条目保持不变）。

        **聚合范围可收窄**（change `0131` / ADR-0124 / 账本 E66）：``session_id`` **非空**时只聚合
        **该会话**的条目（供会话级入口 —— 如 Web 的「压缩本会话记忆」—— 使用，SHALL NOT 顺手提炼
        他会话条目）；**空串**（缺省）保持**全量**语义，逐字与既有行为一致（供循环内节拍压实使用）。
        ``session_id`` 是**收窄范围**的形参，**不是** ``query`` —— 两者语义无干。

        注入 ``compactor`` 时另**逐条目打分写回** ``importance``（0042），并据此对会话做
        **价值门控**：仅有分且最高分低于 ``_CONSOLIDATE_THRESHOLD`` 的会话跳过提炼。
        决策打分本身失败只降级为无决策（不做价值门控），**不**连带阻断固化与遗忘。

        注入 ``summary_promoter``（提升钩子）时，某会话摘要**首次越过**滚动上界
        （``MAX_SUMMARY_CHARS``）即把该摘要条目交付钩子**一次**（供上层落 canonical 真相层；
        change 0153 / 路线图 G3）。缺省 UNWIRED ⇒ 不交付、行为逐字不变。

        注入 ``key_fact_extractor``（结构化抽取器，change 0155 / 路线图 G4）时，对**同一批**被聚合的
        episodic 条目抽取「实体 → 取值」关键事实，落为 ``semantic`` 条目（脱敏后）。缺省 UNWIRED ⇒
        不抽取、行为逐字不变。**抽取不依赖摘要器**：两者独立注入、独立生效。
        """
        decision: DecisionResult | None = None
        if self._compactor is not None:
            items = self.read(query, budget=budget)
            try:
                decision = self._compactor.score(
                    {"query": query, "count": len(items)},
                    [asdict(entry) for entry in items],
                )
            except Exception:  # noqa: BLE001 — 决策分值是咨询性返回值（无写入副作用），
                decision = None  # 其失败不外溢为「固化/遗忘整轮停摆」
        if self._summarizer is not None or self._key_fact_extractor is not None:
            self._summarize_sessions(session_id)
        return decision

    def forget(self, *, threshold: float = _FORGET_THRESHOLD) -> list[MemoryId]:
        """遗忘：衰减评分低于 ``threshold`` 的 **L2 episodic** 条目迁 L4 归档（可逆）。

        评分 ``recency_decay × (1 + log1p(reuse_count)) × (1 + importance)``——新鲜度、
        复用频次与重要度三者皆低才归档；时间未知（``ts<=0``）不惩罚。semantic（提炼产物）、
        L0（人格）与 L3（技能）不参与衰减；**不物理删除**（``audit`` 可见、检索降权）。
        返回被归档条目 id（撤销句柄：``forgetting.<id>``）。
        """
        forgotten: list[MemoryId] = []
        for entry in self._all_entries():
            if entry.kind != "episodic" or entry.layer != "L2":
                continue
            if _decay_score(entry) >= threshold:
                continue
            self.migrate(entry.id, "L2", "L4", trace_id=f"forgetting.{entry.id}")
            forgotten.append(entry.id)
        return forgotten

    # ---- 内部辅助 ----

    def _memo_embedder(self) -> Callable[[list[str]], list[list[float]]]:
        """批量 embedder 的**文本级向量缓存**包装：命中即复用，未变内容零重算。

        每次 ``read`` 对 query 至多向量化一次；条目内容未变则复用缓存向量。首次调用
        失败即置 ``_embed_failed`` 短路（后续直接抛、不再触网），交由 ``relevance`` 的
        词法降级兜底。
        """

        def _embed(texts: list[str]) -> list[list[float]]:
            if self._embed_failed:
                raise RuntimeError("embedder unavailable")  # noqa: TRY003 — 触发词法降级
            keys = [hashlib.blake2b(t.encode("utf-8"), digest_size=16).hexdigest() for t in texts]
            out: list[list[float]] = [self._vectors.get(k, []) for k in keys]
            missing = [
                (i, k, t)
                for i, (k, t) in enumerate(zip(keys, texts, strict=True))
                if k not in self._vectors
            ]
            if missing:
                try:
                    vecs = self._embedder([t for _, _, t in missing])  # type: ignore[misc]
                except Exception:
                    self._embed_failed = True
                    raise
                for (i, k, _), vec in zip(missing, vecs, strict=True):
                    self._vectors[k] = vec
                    out[i] = vec
                self._trim_vectors()
            return out

        return _embed

    def _trim_vectors(self) -> None:
        while len(self._vectors) > _VEC_CACHE_MAX:
            self._vectors.pop(next(iter(self._vectors)))

    def _truncate(self, entries: list[MemoryEntry], budget: int) -> list[MemoryEntry]:
        """按相关度降序保留可容纳条目，**跳过**放不下的（不掐断后续）。

        首条无条件保留（``selected and``），保证预算极小时至少返回最高相关的一条；
        其后超预算的条目只跳过自身，不阻塞更小的低相关条目。
        """
        selected: list[MemoryEntry] = []
        used = 0
        for entry in entries:
            cost = max(1, len(entry.content) // _TOKEN_DIVISOR)
            if selected and used + cost > budget:
                continue
            selected.append(entry)
            used += cost
        return selected

    def _summarize_sessions(self, session_id: str = "") -> None:
        """按会话聚合 episodic 条目 → 打分写回 + 价值门控 → 提炼摘要 → 归档原条目。

        同一循环内亦承载**结构化关键事实抽取**（change 0155）—— 与摘要同材料、同门控、同 trace。
        ``session_id`` 非空 ⇒ 只聚合该会话（change `0131` / E66）；空串 ⇒ 全量（逐字不变）。
        """
        summarizer = self._summarizer
        groups = self._episodic_groups(session_id)
        scores: dict[str, float] = {}
        if self._compactor is not None:
            scores = self._score_importance([e for group in groups.values() for e in group])
        for sid, entries in groups.items():
            if _below_gate(entries, scores):
                continue
            if summarizer is not None:
                prior = self._existing_summary(sid)
                material = [prior, *entries] if prior is not None else entries
                summary = summarizer(material)
                if summary:
                    self._commit_summary(sid, entries, summary)
                    self._deliver_promotion(sid, prior, summary)
            self._extract_key_facts(sid, entries)

    def _score_importance(self, entries: list[MemoryEntry]) -> dict[str, float]:
        """逐条目 importance 打分（judgment ``score`` 原语）并写回（可逆）。

        ``score`` 原语返回的是**条目集的单一分数**，故每条目一次调用；按本地多因子序取前
        ``_MAX_SCORED_PER_COMPACT`` 条，控制单次压实的模型调用数。打分失败（抛错 / 无分值）
        跳过该条目——``importance`` 保持原值，绝不降级写 0（否则一次抖动即清空全库重要度）。
        """
        scorer = self._compactor
        assert scorer is not None  # noqa: S101 — 调用点已判空
        scored: dict[str, float] = {}
        ordered = sorted(entries, key=lambda e: rank(e, ""), reverse=True)
        for entry in ordered[:_MAX_SCORED_PER_COMPACT]:
            state = {
                "entry_id": entry.id,
                "session_id": entry.session_id,
                "layer": entry.layer,
                "reuse_count": entry.reuse_count,
            }
            try:
                result = scorer.score(state, [asdict(entry)])
                value = float(result.answers["score"]["score"])
            except Exception:  # noqa: BLE001 — 打分失败保持原值，不写 0
                continue
            self._write_importance(entry, min(1.0, max(0.0, value)))
            scored[entry.id] = entry.importance
        return scored

    def _write_importance(self, entry: MemoryEntry, value: float) -> None:
        """写回重要度（可逆）：与压实同 trace，回滚该轮即恢复旧值。"""
        previous = entry.importance
        entry.importance = value
        self._backend.put(entry)
        self._hot[entry.id] = entry
        self._tracker.record(
            Effect(
                op="memory.importance",
                target=entry.id,
                undo=lambda: self._restore_importance(entry.id, previous),
                reversible=True,
                coeffect=[],
                trace_id=f"compaction.{entry.session_id or 'default'}",
                ts=time.time(),
            )
        )

    def _episodic_groups(self, session_id: str = "") -> dict[str, list[MemoryEntry]]:
        """L2 事件条目按 ``session_id`` 分组（空会话归 ``""`` 组），保持写入序。

        ``session_id`` 非空 ⇒ 只收该会话的条目（分组后**唯一键**即它本身）；空串 ⇒ 全量。
        """
        groups: dict[str, list[MemoryEntry]] = {}
        for entry in self._all_entries():
            if entry.kind != "episodic" or entry.layer != "L2":
                continue
            if session_id and entry.session_id != session_id:
                continue
            groups.setdefault(entry.session_id, []).append(entry)
        return groups

    def _existing_summary(self, session_id: str) -> MemoryEntry | None:
        """该会话既有摘要条目（无则 ``None``）——滚动合并的「现有摘要」输入。

        id 口径与 ``_commit_summary`` **同一**（``compaction.summary.<key>``，
        ``key = session_id or "default"``）。既有摘要**只被吸收进新摘要**，**不**入迁移列表。
        """
        target = f"compaction.summary.{session_id or 'default'}"
        return next((entry for entry in self._all_entries() if entry.id == target), None)

    def _commit_summary(self, session_id: str, entries: list[MemoryEntry], summary: str) -> None:
        """写摘要条目（tags 带原条目 id 出处）并把原条目迁 L4，同一 trace 可回滚。"""
        key = session_id or "default"
        trace_id = f"compaction.{key}"
        tags = ["compaction", "summary", *[f"from:{entry.id}" for entry in entries]]
        self.write(
            "L2",
            MemoryEntry(
                id=f"compaction.summary.{key}",
                layer="L2",
                content=summary,
                tags=tags,
                source="compaction",
                trace_id=trace_id,
                session_id=session_id,
                kind="semantic",
            ),
        )
        for entry in entries:
            self.migrate(entry.id, "L2", "L4", trace_id=trace_id)

    def _deliver_promotion(self, session_id: str, prior: MemoryEntry | None, summary: str) -> None:
        """半自动提升交付（change 0153 / 路线图 G3）：摘要**首次越过**滚动上界 ⇒ 交付钩子一次。

        判据：既有摘要长度 ≤ ``MAX_SUMMARY_CHARS``（**或该会话尚无既有摘要**）而本次产出摘要长度
        > 上界 ⇒ 越界即滚合并开始截断既有内容（信息正在被销毁），此刻把**刚好完整的**摘要交付
        上层落 canonical 真相层；**已越界**的会话**不再**交付（避免以已稀释的后继摘要覆写）。
        钩子 UNWIRED（缺省）或 ``session_id`` 为空串 ⇒ 不交付；钩子抛错 ⇒ **降级**（`warnings.warn`
        留痕，不牵连压实本身的写回与迁移，不静默吞异常）。
        """
        promoter = self._summary_promoter
        if promoter is None or not session_id:
            return
        if prior is not None and len(prior.content) > MAX_SUMMARY_CHARS:
            return  # 已越界：不再重复交付
        if len(summary) <= MAX_SUMMARY_CHARS:
            return  # 未越界
        entry = self._existing_summary(session_id)
        if entry is None:
            return
        try:
            promoter(session_id, entry)
        except Exception:  # noqa: BLE001 — 钩子失败降级，不牵连压实已完成的写回 / 迁移
            warnings.warn(
                f"summary promotion hook failed for session {session_id!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    def _extract_key_facts(self, session_id: str, entries: list[MemoryEntry]) -> None:
        """结构化关键事实抽取（change 0155 / ADR-0147 / 路线图 G4）。

        先**整批**归一化（脱敏 + 同批归并 + 有界），再落库 —— 归一化阶段任何失败 ⇒ **整批不写**
        （不留半批）。**脱敏在 store 侧无条件执行**：组合根注入的抽取器**不构成信任边界**。裸密钥无
        可用引用 ⇒ 整条丢弃并留痕（留痕含实体名、**不含**取值）。**同批同 slug** ⇒ 只留首条并留痕
        （change 0172）。条目属**全局层**（`session_id` 置空 ⇒ 跨会话可见），产生它的会话经 `tags`
        的 `session:<sid>` 标注溯源。
        """
        extractor = self._key_fact_extractor
        if extractor is None or not entries:
            return
        key = session_id or "default"
        try:
            plan, dropped, deduped = _plan_key_facts(extractor(entries))
        except Exception:  # noqa: BLE001 — 抽取失败降级：整批不写，不牵连压实
            warnings.warn(
                f"key-fact extraction failed for session {key!r}; no key facts were written",
                RuntimeWarning,
                stacklevel=2,
            )
            return
        for fact in plan:
            self._write_key_fact(fact, key=key, session_id=session_id)
        if dropped:
            warnings.warn(
                "key facts dropped (secret-shaped value without a usable reference): "
                f"{', '.join(dropped)}",
                RuntimeWarning,
                stacklevel=2,
            )
        if deduped:
            warnings.warn(
                "key facts deduplicated within one batch (same entity slug; first kept): "
                f"{', '.join(deduped)}",
                RuntimeWarning,
                stacklevel=2,
            )

    def _write_key_fact(self, fact: KeyFact, *, key: str, session_id: str) -> None:
        """落一条关键事实（同实体同一 `id` ⇒ 覆盖式更新、条目不增长）。"""
        slug = slug_entity(fact.entity)
        tags = [_KEY_FACT_TAG, f"entity:{slug}"]
        if fact.ref:
            tags.append(f"ref:{fact.ref}")
        if session_id:
            tags.append(f"session:{key}")
        self.write(
            "L2",
            MemoryEntry(
                id=f"keyfact.{slug}",
                layer="L2",
                content=f"{fact.entity}: {fact.value}",
                tags=tags,
                source="extraction",
                trace_id=f"compaction.{key}",
                session_id="",
                kind="semantic",
            ),
        )

    def _stale_key_facts(self) -> list[MemoryEntry]:
        """识别**失效关键事实**：`tags` 带 `ref:`、该 ref **非** `coeffect:` 形态，且取值已被抹。

        这类条目是 change `0173` 判据修复前的产物（模型自造的出处说明被当成真引用 ⇒ 取值整条被抹）
        ⇒ **已不含任何可用信息**。带 `coeffect:` 引用的条目（引用本身即信息）与无 `ref` 的条目
        不识别。
        """
        stale: list[MemoryEntry] = []
        for entry in self._all_entries():
            if _KEY_FACT_TAG not in entry.tags:
                continue
            refs = [tag[len(_REF_TAG) :] for tag in entry.tags if tag.startswith(_REF_TAG)]
            if not refs or any(ref.startswith(_COEFFECT_REF_PREFIX) for ref in refs):
                continue
            if entry.content.rpartition(": ")[2] != REDACTED:
                continue
            stale.append(entry)
        return stale

    def _material_for_session(self, session_id: str) -> list[MemoryEntry]:
        """该会话的 episodic 材料（**全层** —— 已归档到 L4 的条目同样参与重抽）。

        判据复用 `_episodic_groups`（`kind == "episodic"`）但**去掉 L2 层过滤**：当年抽取时
        它们还是 L2，之后被压实迁到 L4；沿用层过滤会取到空材料 ⇒ 无从重抽。
        """
        tag = f"{_SESSION_TAG}{session_id}"
        return [
            entry
            for entry in self._all_entries()
            if entry.kind == "episodic" and (entry.session_id == session_id or tag in entry.tags)
        ]

    def _delete_entry(self, entry: MemoryEntry) -> None:
        """删除条目（热区 + 后端）并记录进程内可逆效应。

        **持久**可逆性不由这里承担：`EffectTracker` 的 undo 随一次性 CLI 进程结束即失效，
        真正的回滚路径是删除前落的备份文件（见 `repair_stale_key_facts`）。
        """
        self._hot.pop(entry.id, None)
        self._backend.delete(entry.id)
        self._tracker.record(
            Effect(
                op="memory.delete",
                target=entry.id,
                undo=lambda: self._restore_entry(entry),
                reversible=True,
                coeffect=[],
                trace_id=entry.trace_id,
                ts=time.time(),
            )
        )

    def _restore_entry(self, entry: MemoryEntry) -> None:
        """把条目放回后端与热区（`_delete_entry` 的进程内 undo）。"""
        self._backend.put(entry)
        self._hot[entry.id] = entry

    def _group_stale_by_session(
        self, stale: list[MemoryEntry], report: RepairReport
    ) -> dict[str, list[MemoryEntry]]:
        """失效条目按产生它的会话分组；无 `session:` 出处者记入 `skipped`（无材料 ⇒ 不可修复）。"""
        by_session: dict[str, list[MemoryEntry]] = {}
        for entry in stale:
            session_id = next(
                (tag[len(_SESSION_TAG) :] for tag in entry.tags if tag.startswith(_SESSION_TAG)), ""
            )
            if not session_id:
                report.skipped.setdefault("no_session", []).append(entry.id)
                continue
            by_session.setdefault(session_id, []).append(entry)
        return by_session

    def _repair_session(
        self, session_id: str, extractor: KeyFactExtractor, report: RepairReport, written: set[str]
    ) -> None:
        """修一个会话：取材料 → 重抽 → 备份 → 删该会话旧条目（见 `repair_stale_key_facts`）。"""
        try:
            plan, _, _ = _plan_key_facts(extractor(self._material_for_session(session_id)))
        except Exception:  # noqa: BLE001 — 重抽失败 ⇒ 该会话不落库、不删（fail-closed）
            warnings.warn(
                f"key-fact re-extraction failed for session {session_id!r}; nothing was deleted",
                RuntimeWarning,
                stacklevel=2,
            )
            report.skipped.setdefault("extract_failed", []).append(session_id)
            return

        fresh = [f"keyfact.{slug_entity(fact.entity)}" for fact in plan]
        for fact in plan:
            self._write_key_fact(fact, key=session_id, session_id=session_id)
        report.written.extend(fresh)
        written.update(fresh)

        # 该会话产出的**全部旧** keyfact（不止失效者：重抽实体名不保证重合 ⇒ 只删失效者留死条目）
        tag = f"{_SESSION_TAG}{session_id}"
        doomed = [
            entry
            for entry in self._all_entries()
            if _KEY_FACT_TAG in entry.tags and tag in entry.tags and entry.id not in written
        ]
        if not doomed:
            return  # 无可删 ⇒ 不落空备份文件

        backup = _repair_backup_path()
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(
                "".join(json.dumps(asdict(entry), ensure_ascii=False) + "\n" for entry in doomed),
                encoding="utf-8",
            )
        except OSError:
            warnings.warn(
                f"key-fact repair backup failed at {backup}; nothing was deleted",
                RuntimeWarning,
                stacklevel=2,
            )
            report.skipped.setdefault("backup_failed", []).append(session_id)
            return

        report.backup_path = str(backup)
        for entry in doomed:
            self._delete_entry(entry)
            report.deleted.append(entry.id)

    def repair_stale_key_facts(self, *, dry_run: bool = False) -> RepairReport:
        """失效关键事实的运维修复（change 0174 / ADR-0165）：按会话重抽 + 清理该会话旧条目。

        顺序恒为「**先重抽、成功后才清理**」，且删除**排除本次已写入的 id**（同 slug 即覆盖式
        更新，否则刚修好的条目会被自己删掉）。三处 **fail-closed**：抽取器未注入 / 该会话重抽
        抛错 / 备份文件写入失败 ⇒ 均**不删**（宁可不修，不可修坏）。无失效条目 ⇒ 幂等（零写入、
        零备份）。
        """
        report = RepairReport(dry_run=dry_run)
        stale = self._stale_key_facts()
        report.identified = [entry.id for entry in stale]
        by_session = self._group_stale_by_session(stale, report)
        report.sessions = list(by_session)

        extractor = self._key_fact_extractor
        if by_session and extractor is None:
            report.skipped["no_extractor"] = sorted(by_session)
        if not by_session or extractor is None or dry_run:
            return report

        written: set[str] = set()
        for session_id in by_session:
            self._repair_session(session_id, extractor, report, written)
        return report

    def _all_entries(self) -> list[MemoryEntry]:
        """全量条目（冷区 + 热区）：冷区读取失败降级为热区，不抛。"""
        try:
            entries = {entry.id: entry for entry in self._backend.search("")}
        except Exception:  # noqa: BLE001 — 冷区读取失败降级
            entries = {}
        entries.update(self._hot)
        return list(entries.values())

    def _undo_write(self, entry_id: str) -> None:
        self._hot.pop(entry_id, None)
        self._backend.delete(entry_id)

    def _restore_importance(self, entry_id: str, value: float) -> None:
        entry = self._hot.get(entry_id)
        if entry is None:
            return
        entry.importance = value
        self._backend.put(entry)

    def _undo_migrate(self, entry_id: str, from_layer: Layer, to_layer: Layer) -> None:
        entry = self._backend.get(from_layer, entry_id)
        if entry is None:
            entry = self._hot.get(entry_id)
        if entry is None:
            return
        entry.layer = to_layer
        self._backend.put(entry)
        self._hot[entry.id] = entry
