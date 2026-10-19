"""沉淀候选区与晋升（change 0295）：预滤 / 提炼 JSON / 支持度 / 晋升 / prune。

对应规格：doc/openspec/specs/notes/spec.md（沉淀候选区与晋升、存量清理）
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from core.entry import _state_path, main
from core.notes import NoteEntry, NoteError, NoteErrorCode, NoteStore
from core.notes.prune import prune_notes
from core.notes.sediment import (
    CANDIDATE_LIMIT,
    SEDIMENT_SOURCE,
    Candidate,
    CandidateStore,
    Sedimenter,
)

_WRITE_STEP = "tools.file_write（path=a.py）→ 写入成功"
_WRITE_STEP_2 = "tools.code_run（script=pytest）→ 全绿"
_READ_STEP = "tools.file_read（path=a.py）→ 内容"


def _payload(**over: object) -> str:
    base: dict[str, object] = {
        "durable": True,
        "topic": "release-process",
        "title": "发布流程",
        "content": "## 结论\n先跑测试再发布。\n\n## 步骤\n1. 运行 pytest\n2. 打 tag",
        "tags": ["release", "procedure"],
        "queries": ["发布", "release"],
        "kind": "procedure",
    }
    base.update(over)
    return json.dumps(base, ensure_ascii=False)


def _writer(text: str, calls: list[str] | None = None):
    def _write(prompt: str) -> str:
        if calls is not None:
            calls.append(prompt)
        return text

    return _write


def _sedimenter(
    tmp_path: Path,
    payload: str | None = None,
    *,
    auto: bool = False,
    writer=None,
) -> tuple[Sedimenter, NoteStore, list[str]]:
    calls: list[str] = []
    note_store = NoteStore(path=tmp_path / "notes")
    if writer is None:
        writer = _writer(payload if payload is not None else _payload(), calls)
    sedimenter = Sedimenter(
        note_store,
        writer=writer,
        path=tmp_path / "notes-candidates.json",
        auto_promote=auto,
    )
    return sedimenter, note_store, calls


def _observe(sedimenter: Sedimenter, task: str = "整理发布流程文档", steps=None, reply=""):
    return sedimenter.observe_turn(
        task, steps if steps is not None else [_WRITE_STEP], ok=True, reply=reply
    )


# ---- 预滤 ----


@pytest.mark.parametrize(
    ("task", "steps", "ok"),
    [
        ("整理发布流程文档", [_WRITE_STEP], False),
        ("整理发布流程文档", [], True),
        ("整理发布流程文档", [_READ_STEP], True),
        ("写一个吧", [_WRITE_STEP], True),
        ("继续", [_WRITE_STEP], True),
    ],
)
def test_prefilter_never_calls_writer(tmp_path: Path, task, steps, ok) -> None:
    sedimenter, _note_store, calls = _sedimenter(tmp_path)
    assert sedimenter.observe_turn(task, steps, ok=ok, reply="完成") is None
    assert calls == []
    assert sedimenter.list_candidates() == []


def test_no_writer_is_noop(tmp_path: Path) -> None:
    store = NoteStore(path=tmp_path / "notes")
    sedimenter = Sedimenter(store, writer=None, path=tmp_path / "c.json")
    assert sedimenter.observe_turn("整理发布流程", [_WRITE_STEP], ok=True, reply="x") is None
    assert not (tmp_path / "c.json").exists()


# ---- 提炼 JSON ----


def test_valid_json_creates_candidate_with_0600(tmp_path: Path) -> None:
    sedimenter, note_store, calls = _sedimenter(tmp_path)
    candidate = _observe(sedimenter, reply="已发布")
    assert candidate is not None
    assert candidate.candidate_id == "release-process"
    assert candidate.support == 1
    assert candidate.tags == ["release", "procedure"]
    assert candidate.queries == ["发布", "release"]
    assert candidate.kind == "procedure"
    assert candidate.evidence == "整理发布流程文档"
    assert len(calls) == 1
    assert note_store.list() == [], "候选不得直写 canonical"
    path = tmp_path / "notes-candidates.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600  # noqa: PLR2004 — 0600 权限


def test_fenced_json_is_tolerated(tmp_path: Path) -> None:
    sedimenter, _store, _calls = _sedimenter(tmp_path, f"```json\n{_payload()}\n```")
    assert _observe(sedimenter) is not None


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        _payload(durable=False),
        _payload(content=""),
        _payload(topic="!!!"),
        _payload(topic=123),
    ],
)
def test_invalid_or_non_durable_is_dropped(tmp_path: Path, payload: str) -> None:
    sedimenter, _store, _calls = _sedimenter(tmp_path, payload)
    assert _observe(sedimenter) is None
    assert sedimenter.list_candidates() == []


def test_topic_is_slugified_and_fields_bounded(tmp_path: Path) -> None:
    payload = _payload(topic="Release Process!", title="T" * 500, content="C" * 5000)
    sedimenter, _store, _calls = _sedimenter(tmp_path, payload)
    candidate = _observe(sedimenter)
    assert candidate is not None
    assert candidate.candidate_id == "release-process"
    assert len(candidate.title) == 120  # noqa: PLR2004 — 标题上界
    assert len(candidate.content) == 4000  # noqa: PLR2004 — 正文上界


def test_writer_failure_is_swallowed(tmp_path: Path) -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("model down")  # noqa: TRY003

    store = NoteStore(path=tmp_path / "notes")
    sedimenter = Sedimenter(store, writer=boom, path=tmp_path / "c.json")
    assert sedimenter.observe_turn("整理发布流程", [_WRITE_STEP], ok=True, reply="x") is None
    assert sedimenter.list_candidates() == []


# ---- 支持度与上限 ----


def test_same_trace_does_not_inflate_support(tmp_path: Path) -> None:
    sedimenter, _store, _calls = _sedimenter(tmp_path)
    _observe(sedimenter)
    candidate = _observe(sedimenter)
    assert candidate is not None
    assert candidate.support == 1
    assert len(sedimenter.list_candidates()) == 1


def test_distinct_trace_increments_support(tmp_path: Path) -> None:
    sedimenter, _store, _calls = _sedimenter(tmp_path)
    _observe(sedimenter)
    candidate = _observe(sedimenter, steps=[_WRITE_STEP_2])
    assert candidate is not None
    assert candidate.support == 2  # noqa: PLR2004 — 两条不同轨迹各 +1


def test_store_is_bounded(tmp_path: Path) -> None:
    now = [0.0]
    store = CandidateStore(tmp_path / "c.json", limit=3, clock=lambda: now[0])
    for i in range(4):
        now[0] += 1
        store.upsert(Candidate(candidate_id=f"c{i}", title=str(i)), trace_digest=f"d{i}")
    ids = [c.candidate_id for c in store.list()]
    assert len(ids) == 3  # noqa: PLR2004 — 上限
    assert "c0" not in ids


def test_corrupt_store_degrades_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.warns(UserWarning):
        store = CandidateStore(path)
    assert store.list() == []


def test_candidates_are_invisible_to_canonical_surfaces(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path)
    _observe(sedimenter)
    assert note_store.list() == []
    assert note_store.search("发布") == []
    assert "release-process" not in note_store.digest("发布流程")


# ---- 晋升 ----


def test_promote_writes_canonical(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path)
    _observe(sedimenter)
    note = sedimenter.promote("release-process")
    assert note.note_id == "release-process"
    assert note.source == SEDIMENT_SOURCE
    assert note.title == "发布流程"
    assert "sediment:release-process" in note.tags
    assert note.search_queries == ["发布", "release"]
    assert sedimenter.list_candidates() == []
    loaded = note_store.get("release-process")
    assert loaded.source == SEDIMENT_SOURCE
    assert "先跑测试再发布" in loaded.content


def test_promote_preserves_pinned_and_priority(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path)
    note_store.update(
        NoteEntry(
            note_id="release-process",
            title="旧",
            content="旧正文",
            tags=["sediment:release-process"],
            source=SEDIMENT_SOURCE,
            pinned=True,
            pin_priority=100,
        )
    )
    _observe(sedimenter)
    note = sedimenter.promote("release-process")
    assert note.pinned is True
    assert note.pin_priority == 100  # noqa: PLR2004
    assert "先跑测试再发布" in note.content


def test_promote_refuses_foreign_source(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path)
    note_store.update(NoteEntry(note_id="release-process", title="人工", content="人工正文"))
    _observe(sedimenter)
    with pytest.raises(NoteError) as exc:
        sedimenter.promote("release-process")
    assert exc.value.code == NoteErrorCode.TOPIC_EXISTS
    assert note_store.get("release-process").content == "人工正文"
    assert len(sedimenter.list_candidates()) == 1


def test_promote_refuses_other_candidate_target(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path)
    note_store.update(
        NoteEntry(
            note_id="shared",
            title="A",
            content="A 正文",
            tags=["sediment:other"],
            source=SEDIMENT_SOURCE,
        )
    )
    _observe(sedimenter)
    with pytest.raises(NoteError):
        sedimenter.promote("release-process", as_topic="shared")
    assert note_store.get("shared").content == "A 正文"
    assert len(sedimenter.list_candidates()) == 1


def test_auto_promote_default_off(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path)
    _observe(sedimenter)
    _observe(sedimenter, steps=[_WRITE_STEP_2])
    assert note_store.list() == []
    assert sedimenter.list_candidates()[0].support == 2  # noqa: PLR2004 — 支持度阈值


def test_auto_promote_on_at_two_supports(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path, auto=True)
    _observe(sedimenter)
    assert note_store.list() == [], "1 条支持不自动晋升"
    _observe(sedimenter, steps=[_WRITE_STEP_2])
    assert note_store.get("release-process").source == SEDIMENT_SOURCE
    assert sedimenter.list_candidates() == []


def test_reject_removes_candidate(tmp_path: Path) -> None:
    sedimenter, note_store, _calls = _sedimenter(tmp_path)
    _observe(sedimenter)
    assert sedimenter.reject("release-process") is True
    assert sedimenter.list_candidates() == []
    assert note_store.list() == []


# ---- prune ----


def _seed_note(store: NoteStore, note_id: str, *, source: str, pinned: bool = False) -> None:
    store.update(
        NoteEntry(note_id=note_id, title=note_id, content="正文", source=source, pinned=pinned)
    )


def test_prune_moves_only_matching_source(tmp_path: Path) -> None:
    notes = NoteStore(path=tmp_path / "notes")
    _seed_note(notes, "a", source="notes.turn")
    _seed_note(notes, "b", source="notes.turn")
    _seed_note(notes, "keep", source="notes.promote")
    raw_a = notes.raw("a")

    result = prune_notes(notes, source="notes.turn", trash_dir=tmp_path / "trash")

    assert result.moved == ["a", "b"]
    assert result.trash_path is not None
    assert (result.trash_path / "a.md").read_text(encoding="utf-8") == raw_a
    assert [n.note_id for n in notes.list()] == ["keep"]
    manifest = json.loads((result.manifest_path or Path()).read_text(encoding="utf-8"))
    assert manifest["source"] == "notes.turn"
    assert manifest["moved"] == ["a", "b"]
    assert stat.S_IMODE((result.manifest_path or Path()).stat().st_mode) == 0o600  # noqa: PLR2004


def test_prune_keeps_pinned_by_default(tmp_path: Path) -> None:
    notes = NoteStore(path=tmp_path / "notes")
    _seed_note(notes, "p", source="notes.turn", pinned=True)
    _seed_note(notes, "n", source="notes.turn")

    result = prune_notes(notes, source="notes.turn", trash_dir=tmp_path / "trash")

    assert result.moved == ["n"]
    assert result.kept_pinned == ["p"]
    assert notes.get("p").pinned is True


def test_prune_dry_run_does_not_touch_disk(tmp_path: Path) -> None:
    notes = NoteStore(path=tmp_path / "notes")
    _seed_note(notes, "a", source="notes.turn")
    result = prune_notes(notes, source="notes.turn", trash_dir=tmp_path / "trash", dry_run=True)
    assert result.moved == ["a"]
    assert result.trash_path is None
    assert not (tmp_path / "trash").exists()
    assert notes.get("a").note_id == "a"


def test_prune_zero_moved_returns_empty(tmp_path: Path) -> None:
    notes = NoteStore(path=tmp_path / "notes")
    _seed_note(notes, "p", source="notes.promote")
    result = prune_notes(notes, source="notes.turn", trash_dir=tmp_path / "trash")
    assert result.moved == []
    assert not (tmp_path / "trash").exists()


def test_prune_trash_is_restorable(tmp_path: Path) -> None:
    notes = NoteStore(path=tmp_path / "notes")
    _seed_note(notes, "a", source="notes.turn")
    raw = notes.raw("a")
    result = prune_notes(notes, source="notes.turn", trash_dir=tmp_path / "trash")
    assert raw is not None
    trash_file = (result.trash_path or Path()) / "a.md"
    assert trash_file.read_text(encoding="utf-8") == raw


# ---- CLI ----


def _seed_candidate(candidate_id: str = "release-process") -> None:
    CandidateStore(_state_path("notes-candidates.json")).upsert(
        Candidate(
            candidate_id=candidate_id,
            title="发布流程",
            content="## 结论\n先跑测试",
            tags=["release"],
            queries=["发布"],
        ),
        trace_digest="d",
    )


def test_cli_candidates_and_promote(capsys: pytest.CaptureFixture[str]) -> None:
    _seed_candidate()
    assert main(["notes", "candidates"]) == 0
    out = capsys.readouterr().out
    assert "release-process" in out and "发布流程" in out

    assert main(["notes", "candidate-promote", "release-process"]) == 0
    assert "release-process" in capsys.readouterr().out
    store = NoteStore(path=_state_path("notes"))
    assert store.get("release-process").source == SEDIMENT_SOURCE
    assert main(["notes", "candidates"]) == 0
    assert "（无候选）" in capsys.readouterr().out


def test_cli_candidate_reject(capsys: pytest.CaptureFixture[str]) -> None:
    _seed_candidate()
    assert main(["notes", "candidate-reject", "release-process"]) == 0
    assert main(["notes", "candidate-show", "release-process"]) == 1


def test_cli_prune_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    store = NoteStore(path=_state_path("notes"))
    _seed_note(store, "a", source="notes.turn")
    assert main(["notes", "prune", "--source", "notes.turn", "--dry-run"]) == 0
    assert "a" in capsys.readouterr().out
    assert main(["notes", "prune", "--source", "notes.turn"]) == 0
    assert store.list() == []
    assert main(["notes", "prune", "--source", "notes.turn"]) == 1


def test_candidate_limit_constant_is_128() -> None:
    assert CANDIDATE_LIMIT == 128  # noqa: PLR2004 — 规格固定上界
