"""失效关键事实的运维修复（keyfact repair）单测。

对应规格：doc/openspec/specs/memory/spec.md「失效关键事实的运维修复」
（change 0174 / ADR-0165 / 台账 E111）。

覆盖：识别判据 / 按会话重抽（含 L4 材料）· 清理旧条目（含同 slug 不误删）· 三处 fail-closed
（抽取器未注入 / 抽取失败 / 备份写入失败）· 备份文件 · 幂等 · 只读预演 · 无会话出处不删。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory import REDACTED, KeyFact, MemoryEntry, MemoryStore, slug_entity

# 模型自造的出处说明（change 0173 判据修复前的产物形态）
_BOGUS_REF = "round1:热带水果有哪些"


def _episodic(
    entry_id: str, session_id: str, content: str = "round 1 ok\n事件", *, layer: str = "L2"
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,  # type: ignore[arg-type]
        content=content,
        tags=["loop"],
        source="loop",
        session_id=session_id,
        kind="episodic",
        trace_id="t",
    )


def _keyfact(
    entity: str,
    value: str,
    ref: str = "",
    *,
    session: str = "s1",
) -> MemoryEntry:
    """造一条 keyfact 条目（口径同 `_write_key_fact`：id 走 slug 归一、ref/session 落 tags）。"""
    tags = ["key_fact", f"entity:{entity}"]
    if ref:
        tags.append(f"ref:{ref}")
    if session:
        tags.append(f"session:{session}")
    return MemoryEntry(
        id=f"keyfact.{slug_entity(entity)}",
        layer="L2",
        content=f"{entity}: {value}",
        tags=tags,
        source="extraction",
        session_id="",
        kind="semantic",
        trace_id=f"compaction.{session or 'default'}",
    )


def _store(facts: list[KeyFact] | None) -> MemoryStore:
    """注入「定值抽取器」的 store；``facts=None`` ⇒ **不注入**抽取器。"""
    if facts is None:
        return MemoryStore()
    return MemoryStore(key_fact_extractor=lambda entries: list(facts))


def _contents(store: MemoryStore) -> dict[str, str]:
    return {str(e.id): e.content for e in store.audit()}


def _backups(state_dir: Path) -> list[Path]:
    return sorted(state_dir.glob("memory.repair.*.jsonl"))


# ---- 识别判据 ----


def test_identifies_only_stale_entries() -> None:
    """只识别「ref 非 coeffect: 形态 + 取值已被抹」者；coeffect 引用条目与正常条目不误伤。"""
    store = _store(None)
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("数据库口令", REDACTED, "coeffect:DB_PASSWORD"))
    store.write("L2", _keyfact("项目名称", "core-agent"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))

    report = store.repair_stale_key_facts(dry_run=True)

    assert report.identified == ["keyfact.榴莲"]
    assert report.deleted == []


def test_stale_without_session_tag_is_not_deleted() -> None:
    """无 `session:` 出处的失效条目 ⇒ 无材料可重抽 ⇒ 不删、报告标明不可修复。"""
    store = _store([KeyFact(entity="榴莲", value="水果之王")])
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF, session=""))

    report = store.repair_stale_key_facts()

    assert "keyfact.榴莲" not in report.deleted
    assert "keyfact.榴莲" in report.skipped["no_session"]
    assert _contents(store)["keyfact.榴莲"] == f"榴莲: {REDACTED}"


# ---- 重抽与清理 ----


def test_successful_reextract_clears_all_old_entries_of_the_session() -> None:
    """重抽成功 ⇒ 该会话全部旧 keyfact 被删（含重抽**未**再产出的实体名），新条目落库。"""
    facts = [
        KeyFact(entity="榴莲", value="被称为水果之王"),
        KeyFact(entity="泰国", value="东南亚水果王国"),
    ]
    store = _store(facts)
    store.write("L2", _episodic("e0", "s1", "round 1 ok\n热带水果与产地"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))
    store.write("L2", _keyfact("山竹", REDACTED, _BOGUS_REF))

    report = store.repair_stale_key_facts()
    got = _contents(store)

    assert "keyfact.山竹" in report.deleted  # 重抽未再产出 ⇒ 仍清掉
    assert "keyfact.山竹" not in got
    assert got["keyfact.榴莲"] == "榴莲: 被称为水果之王"  # 同 slug ⇒ 覆盖为新值
    assert got["keyfact.泰国"] == "泰国: 东南亚水果王国"
    assert report.backup_path  # 有删除 ⇒ 必有备份


def test_same_slug_rewrite_is_not_deleted() -> None:
    """同 slug 命中时，刚写好的条目 SHALL NOT 出现在被删集合（不得自己删自己）。"""
    store = _store([KeyFact(entity="榴莲", value="被称为水果之王")])
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))

    report = store.repair_stale_key_facts()

    assert "keyfact.榴莲" not in report.deleted
    assert _contents(store)["keyfact.榴莲"] == "榴莲: 被称为水果之王"


def test_material_includes_archived_l4_entries() -> None:
    """材料取自全层：会话的 episodic 原文已归档到 L4 时仍能重抽。"""
    store = _store([KeyFact(entity="Textual版本", value="8.2.8")])
    store.write("L4", _episodic("loop.t1", "s1", "round 1 ok\n依赖 Textual 8.2.8", layer="L4"))
    store.write("L2", _keyfact("Textual 依赖版本", REDACTED, "会话事件"))

    report = store.repair_stale_key_facts()

    assert report.sessions == ["s1"]
    assert _contents(store)[f"keyfact.{slug_entity('Textual版本')}"] == "Textual版本: 8.2.8"
    assert f"keyfact.{slug_entity('Textual 依赖版本')}" not in _contents(store)


# ---- fail-closed 三处 ----


def test_no_extractor_means_no_deletion() -> None:
    """抽取器未注入 ⇒ 不重抽、不删、不落备份（宁可不修，不可修坏）。"""
    store = _store(None)
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))
    before = _contents(store)

    report = store.repair_stale_key_facts()

    assert report.deleted == []
    assert report.backup_path == ""
    assert "no_extractor" in report.skipped
    assert _contents(store) == before


def test_extractor_failure_means_no_deletion() -> None:
    """某会话重抽抛错 ⇒ 该会话不落库、不删；其余会话照常处理。"""

    def _boom(entries: list[MemoryEntry]) -> list[KeyFact]:
        raise RuntimeError("抽取器崩了")

    store = MemoryStore(key_fact_extractor=_boom)
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))

    report = store.repair_stale_key_facts()

    assert report.deleted == []
    assert "s1" in report.skipped["extract_failed"]
    assert _contents(store)["keyfact.榴莲"] == f"榴莲: {REDACTED}"


def test_backup_failure_means_no_deletion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """备份文件写入失败 ⇒ 不删任何条目（新落条目保留）。"""
    # 把状态目录指向一个**文件**：备份路径写入必失败（NotADirectoryError）
    not_a_dir = tmp_path / "not-a-dir"
    not_a_dir.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CORE_STATE_DIR", str(not_a_dir))

    store = _store([KeyFact(entity="榴莲", value="被称为水果之王")])
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))
    store.write("L2", _keyfact("山竹", REDACTED, _BOGUS_REF))

    report = store.repair_stale_key_facts()

    assert report.deleted == []
    assert report.backup_path == ""
    assert "backup_failed" in report.skipped
    assert _contents(store)["keyfact.山竹"] == f"山竹: {REDACTED}"  # 旧条目留在原地


# ---- 备份文件 ----


def test_backup_file_keeps_original_entries() -> None:
    """备份文件逐行 = 被删条目原文（可直接解析回条目）。"""
    store = _store([KeyFact(entity="泰国", value="东南亚水果王国")])
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))
    store.write("L2", _keyfact("山竹", REDACTED, _BOGUS_REF))

    report = store.repair_stale_key_facts()

    raw = Path(report.backup_path).read_text(encoding="utf-8")
    rows = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
    assert {r["id"] for r in rows} == set(report.deleted)
    assert {r["id"]: r["content"] for r in rows}["keyfact.榴莲"] == f"榴莲: {REDACTED}"
    assert all(r["tags"] for r in rows)


# ---- 幂等与预演 ----


def test_idempotent_when_no_stale_entries(tmp_path: Path) -> None:
    """无失效条目 ⇒ 不产生任何写入（含不落备份）。"""
    store = _store([KeyFact(entity="X", value="Y")])
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("项目名称", "core-agent"))
    before = _contents(store)

    report = store.repair_stale_key_facts()

    assert (report.identified, report.deleted, report.written) == ([], [], [])
    assert report.backup_path == ""
    assert _contents(store) == before
    assert _backups(tmp_path / "state") == []


def test_dry_run_reports_but_never_writes(tmp_path: Path) -> None:
    """只读预演：报告识别结果与将清理条数，不删、不落库、不落备份。"""
    store = _store([KeyFact(entity="榴莲", value="被称为水果之王")])
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))
    before = _contents(store)

    report = store.repair_stale_key_facts(dry_run=True)

    assert report.dry_run is True
    assert report.identified == ["keyfact.榴莲"]
    assert report.sessions == ["s1"]
    assert report.deleted == [] and report.written == []
    assert report.backup_path == ""
    assert _contents(store) == before
    assert _backups(tmp_path / "state") == []


def test_empty_reextract_result_still_clears_stale_entries() -> None:
    """重抽返回**合法空**（模型明确无可抽）⇒ 视为成功 ⇒ 旧条目仍清（它们已无信息）。"""
    store = _store([])
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _keyfact("榴莲", REDACTED, _BOGUS_REF))

    report = store.repair_stale_key_facts()

    assert report.deleted == ["keyfact.榴莲"]
    assert "keyfact.榴莲" not in _contents(store)
