"""文档化记忆（notes）单测：canonical Markdown 渲染/解析 + MarkdownBackend + NoteStore。

对应规格：doc/openspec/specs/notes/spec.md
接口设计：doc/03-interfaces/notes-interface.md
"""

from __future__ import annotations

import pytest

from core.memory import MemoryEntry
from core.notes import (
    MarkdownBackend,
    NoteEntry,
    NoteError,
    NoteErrorCode,
    NoteStore,
    parse_note,
    render_note,
    slug_topic,
)


def _entry(note: NoteEntry) -> MemoryEntry:
    """NoteEntry → MemoryEntry 信封（content = canonical 全文，自描述）。"""
    return MemoryEntry(
        id=note.note_id,
        layer="L2",
        content=render_note(note),
        tags=list(note.tags),
        source=note.source,
        trace_id="notes",
    )


# ---- models：渲染 / 解析往返 ----


def test_render_parse_roundtrip() -> None:
    updated_at = 123.0
    note = NoteEntry(
        note_id="n1",
        title="标题",
        content="正文行1\n\n正文行2",
        tags=["a", "b"],
        search_queries=["q1", "q2"],
        source="notes",
        updated_at=updated_at,
    )
    got = parse_note(render_note(note), note_id="n1")
    assert got.title == "标题"
    assert got.tags == ["a", "b"]
    assert got.content == "正文行1\n\n正文行2"
    assert got.search_queries == ["q1", "q2"]
    assert got.updated_at == updated_at
    assert got.source == "notes"


def test_slug_topic_keeps_cjk_and_folds_punct() -> None:
    assert slug_topic("修复 登录 超时!") == "修复-登录-超时"
    assert slug_topic("Fix the Login Timeout") == "fix-the-login-timeout"
    assert slug_topic("!!!") == ""


# ---- MarkdownBackend：覆盖式 / 原子 / 清单 / 词法检索 ----


def test_backend_put_is_overwrite(tmp_path) -> None:
    backend = MarkdownBackend(tmp_path)
    backend.put(_entry(NoteEntry(note_id="topic", title="T", content="version 1")))
    backend.put(_entry(NoteEntry(note_id="topic", title="T", content="version 2")))
    raw = (tmp_path / "topic.md").read_text(encoding="utf-8")
    assert "version 2" in raw
    assert "version 1" not in raw  # 覆盖式，非两段拼接


def test_backend_atomic_write_keeps_previous_on_failure(tmp_path, monkeypatch) -> None:
    backend = MarkdownBackend(tmp_path)
    backend.put(_entry(NoteEntry(note_id="t", title="T", content="v1")))
    before = (tmp_path / "t.md").read_text(encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("replace failed")  # noqa: TRY003 — 测试用哨兵异常

    monkeypatch.setattr("core.notes.backend.os.replace", boom)
    with pytest.raises(OSError):
        backend.put(_entry(NoteEntry(note_id="t", title="T", content="v2")))
    # 替换前中断 ⇒ canonical 文件仍是旧内容（不出现半截）
    assert (tmp_path / "t.md").read_text(encoding="utf-8") == before


def test_backend_list_index_and_get_roundtrip(tmp_path) -> None:
    backend = MarkdownBackend(tmp_path)
    backend.put(_entry(NoteEntry(note_id="a", title="A", content="正文A", tags=["x"])))
    backend.put(_entry(NoteEntry(note_id="b", title="B", content="正文B")))

    index = backend.list_index()
    assert sorted(note_id for note_id, _ in index.entries) == ["a", "b"]

    got = backend.get("L2", "a")
    assert got is not None
    assert got.tags == ["x"]
    assert parse_note(got.content, note_id="a").content == "正文A"
    assert backend.get("L2", "missing") is None


def test_backend_search_hits_search_queries(tmp_path) -> None:
    backend = MarkdownBackend(tmp_path)
    # 关键词只在头部 `## Search Queries`，正文不含 —— 仍须命中（纯词法，无向量库）
    backend.put(
        _entry(
            NoteEntry(
                note_id="alpha",
                title="Alpha",
                content="本段不含关键词",
                search_queries=["alpha-widget"],
            )
        )
    )
    backend.put(_entry(NoteEntry(note_id="beta", title="Beta", content="无关")))

    hits = backend.search("alpha-widget")
    assert [hit.id for hit in hits] == ["alpha"]


def test_backend_search_matches_cjk_sentence_query(tmp_path) -> None:
    """中文任务句（无空格）按 2-gram 切词命中 —— Consult 的实际查询形态。"""
    backend = MarkdownBackend(tmp_path)
    backend.put(_entry(NoteEntry(note_id="部署", title="部署流程", content="先备份再滚动更新")))
    backend.put(_entry(NoteEntry(note_id="报销", title="报销单据", content="贴票即可")))

    hits = backend.search("部署流程怎么走")

    assert [hit.id for hit in hits] == ["部署"], "长句经 2-gram 命中标题，不因无空格而空手"
    assert backend.search("报销单据")[0].id == "报销", "另一主题仍可独立命中"


def test_backend_search_weights_title_above_content(tmp_path) -> None:
    """字段加权（change 0107）：标题精确命中排在「正文顺带提及」之前，两者均命中。"""
    backend = MarkdownBackend(tmp_path)
    backend.put(
        _entry(NoteEntry(note_id="alpha", title="无关标题", content="正文里顺带提到 部署 一词"))
    )
    backend.put(_entry(NoteEntry(note_id="beta", title="部署流程", content="无关正文")))

    hits = backend.search("部署")

    assert [hit.id for hit in hits] == ["beta", "alpha"], "标题命中优先（加权只改排序、不改过滤）"


def test_backend_search_weights_meta_above_content(tmp_path) -> None:
    """tags / `## Search Queries` 权重高于正文 —— 语义浓缩元数据买得到排名。"""
    backend = MarkdownBackend(tmp_path)
    backend.put(_entry(NoteEntry(note_id="alpha", title="A", content="正文顺带提到 alpha-widget")))
    backend.put(
        _entry(
            NoteEntry(note_id="beta", title="B", content="无关", search_queries=["alpha-widget"])
        )
    )

    hits = backend.search("alpha-widget")

    assert [hit.id for hit in hits] == ["beta", "alpha"]


def test_backend_search_no_hit_returns_empty(tmp_path) -> None:
    """加权不改过滤：无任何字段命中 ⇒ 空列表（分区加权不得凭空产生 >0 分）。"""
    backend = MarkdownBackend(tmp_path)
    backend.put(_entry(NoteEntry(note_id="alpha", title="Alpha", content="正文")))

    assert backend.search("完全不相干的词") == []


# ---- NoteStore：读写闭环 / 错误码 / 循环接缝 ----


def test_store_consult_update_consult_reads_latest(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    store.update(NoteEntry(note_id="topic", title="主题", content="旧结论"))
    first = store.consult("主题")
    assert first and "旧结论" in first[0].content

    store.update(NoteEntry(note_id="topic", title="主题", content="新结论"))
    second = store.consult("主题")
    assert second and "新结论" in second[0].content
    assert "旧结论" not in second[0].content


def test_store_get_missing_raises(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    with pytest.raises(NoteError) as excinfo:
        store.get("missing")
    assert excinfo.value.code is NoteErrorCode.NOTE_NOT_FOUND


def test_store_create_topic_exists_but_ensure_is_idempotent(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    store.create("dup", title="Dup", content="first")
    with pytest.raises(NoteError) as excinfo:
        store.create("dup", title="Dup", content="second")
    assert excinfo.value.code is NoteErrorCode.TOPIC_EXISTS
    # 显式 create 被拒后既有内容不被覆盖
    assert store.get("dup").content == "first"
    # ensure 幂等：已存在直接返回，不报错
    assert store.ensure("dup").note_id == "dup"
    assert store.ensure("fresh").note_id == "fresh"


def test_store_observe_turn_writes_canonical(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    note = store.observe_turn("修复 登录 超时", ["定位到 token 过期", "刷新 token"], ok=True)
    assert note is not None
    raw = (tmp_path / f"{note.note_id}.md").read_text(encoding="utf-8")
    assert "刷新 token" in raw
    # 失败轮不写盘
    assert store.observe_turn("另一任务", ["x"], ok=False) is None


def test_store_digest_carries_hits_and_catalog(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    store.update(NoteEntry(note_id="deploy", title="部署流程", content="先备份再滚动更新"))
    store.update(NoteEntry(note_id="other", title="其他主题", content="无关"))
    digest = store.digest("部署流程")
    assert "部署流程" in digest  # 命中摘要
    assert "other" in digest  # 笔记清单（全量标题，不含正文）
