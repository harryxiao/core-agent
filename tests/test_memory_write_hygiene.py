"""记忆写回卫生（change 0254 / ADR-0245）：脱敏 / 有界 / 空值拒收 / 陈旧清理。

审计（2026-10-17）确认默认写入路径存在四处明文面与两处压实硬伤；本文件按规格新增的
四条 ADDED Requirement 逐条锚定。全部用例只依赖公开构造面与既有注入缝。
"""

from __future__ import annotations

from pathlib import Path

from core.context import Compaction, Compactor
from core.memory import MemoryEntry, MemoryStore
from core.memory.extract import KeyFact, scrub_key_fact
from core.notes import NoteStore
from core.skills import SkillLibrary, SkillRouter, SopExtractor

_SECRET = "sk-abcdefgh12345678"


def test_notes_turn_redacts_secret_before_write(tmp_path: Path) -> None:
    """notes 写回正文逐行脱敏：命中段 `<redacted>`，工具名与路径仍在。"""
    store = NoteStore(path=tmp_path)
    step = f"tools.code_run（script: export KEY={_SECRET} && ./deploy.sh）→ 部署完成"
    note = store.observe_turn("部署 service-a", [step], ok=True)
    assert note is not None
    assert _SECRET not in note.content
    assert "<redacted>" in note.content
    assert "tools.code_run" in note.content and "./deploy.sh" in note.content


def test_compaction_products_are_redacted_and_bounded() -> None:
    """压实产物单条脱敏 + 有界（脱敏后截断）。"""
    store = MemoryStore()
    Compactor(memory=store).persist(
        Compaction(
            conclusions=[f"结论：使用 {_SECRET} 完成部署", "结论：" + "长" * 1000],
        ),
        session_id="s1",
    )
    entries = {entry.id: entry for entry in store.audit()}
    first = entries["compaction.fact.s1.0"].content
    second = entries["compaction.fact.s1.1"].content
    assert _SECRET not in first and "<redacted>" in first
    assert len(second) <= 400  # noqa: PLR2004 — 单条字符上界
    assert "结论：" in second


def test_compaction_prunes_stale_product_slots() -> None:
    """同会话本轮条目更少 ⇒ 旧序号条目被删除（不残留陈旧事实）。"""
    store = MemoryStore()
    compactor = Compactor(memory=store)
    compactor.persist(Compaction(conclusions=["结论 A", "结论 B", "结论 C"]), session_id="s1")
    compactor.persist(Compaction(conclusions=["结论 D"]), session_id="s1")
    ids = {entry.id for entry in store.audit()}
    assert "compaction.fact.s1.0" in ids
    assert "compaction.fact.s1.1" not in ids
    assert "compaction.fact.s1.2" not in ids


def test_router_miss_is_redacted_and_bounded() -> None:
    """路由未命中正文脱敏 + 有界；同一任务仍幂等为一条。"""
    memory = MemoryStore()
    router = SkillRouter(SkillLibrary(), memory=memory)
    task = f"整理 {_SECRET} 的票据 " + "长" * 800
    router.match(task, session_id="s1")
    router.match(task, session_id="s1")
    entries = [entry for entry in memory.audit() if entry.source == "skills"]
    assert len(entries) == 1
    assert _SECRET not in entries[0].content
    assert "<redacted>" in entries[0].content
    assert len(entries[0].content) <= len("路由未命中: ") + 400


def test_sop_instructions_are_redacted_before_register() -> None:
    """SOP 提炼正文入口脱敏：入库 instructions 不含密钥明文。"""
    library = SkillLibrary()
    extractor = SopExtractor(
        library,
        writer=lambda _prompt: f"1. 调用 {_SECRET} 对应接口\n2. 校验返回码",
        threshold=1,
    )
    skill = extractor.observe("发布服务", ["tools.code_run（…）→ ok"], ok=True)
    assert skill is not None
    assert _SECRET not in skill.instructions
    assert "<redacted>" in skill.instructions


def test_empty_key_fact_value_is_dropped_without_overwrite() -> None:
    """空 entity/value 丢弃；空值不得覆盖既有事实。"""
    assert scrub_key_fact(KeyFact(entity="service-a", value="   ")) is None
    assert scrub_key_fact(KeyFact(entity="service-a", value="", ref="coeffect:db")) is None

    store = MemoryStore(key_fact_extractor=lambda _entries: [KeyFact("service-a", "   ")])  # type: ignore[arg-type]
    store.write(
        "L2",
        MemoryEntry(
            id="keyfact.service-a",
            layer="L2",
            content="service-a: good",
            tags=["key_fact", "entity:service-a"],
            source="extraction",
            trace_id="compaction.s1",
            session_id="",
            kind="semantic",
        ),
    )
    store._extract_key_facts(  # type: ignore[reportPrivateUsage]  # noqa: SLF001 — 抽取接缝直测
        "s1", [store.audit("compaction.s1")[0]]
    )
    entry = store._entry_by_id("keyfact.service-a")  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    assert entry is not None and entry.content == "service-a: good"
