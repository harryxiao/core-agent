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
from core.notes.store import _MAX_PINNED_CHARS


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


# ---- 常驻（pinned）笔记（change 0149 / ADR-0141 / 账本 E93） ----


def test_render_note_omits_pinned_line_when_false() -> None:
    """`pinned=False` ⇒ 渲染逐字不变（零回归护栏：既有 canonical 文件字节不动）。"""
    note = NoteEntry(note_id="t", title="T", content="body", updated_at=0.0)
    expected = (
        "# T\n"
        "\n"
        "- id: t\n"
        "- tags: \n"
        "- source: notes\n"
        "- updated_at: 0.0\n"
        "\n"
        "## Search Queries\n"
        "\n"
        "- T\n"
        "\n"
        "## Notes\n"
        "\n"
        "body\n"
    )
    assert render_note(note) == expected
    assert "- pinned" not in render_note(note)


def test_render_parse_roundtrip_with_pinned() -> None:
    note = NoteEntry(note_id="constraints", title="硬约束", content="接口必须 HTTPS", pinned=True)
    rendered = render_note(note)
    assert "- pinned: true" in rendered
    got = parse_note(rendered, note_id="constraints")
    assert got.pinned is True
    assert got.content == "接口必须 HTTPS"


@pytest.mark.parametrize(
    "spelling", ["true", "True", "TRUE", "yes", "Yes", "1", "on", "ON", " true "]
)
def test_parse_note_pinned_truthy_spellings(spelling: str) -> None:
    text = f"# T\n\n- id: t\n- pinned: {spelling}\n\n## Notes\n\nbody\n"
    assert parse_note(text, note_id="t").pinned is True


@pytest.mark.parametrize("spelling", ["false", "no", "0", "off", "", "maybe", "pinneed"])
def test_parse_note_pinned_falsey_spellings(spelling: str) -> None:
    """无法识别的取值一律 False（fail-closed：手误不得意外置常驻）。"""
    text = f"# T\n\n- id: t\n- pinned: {spelling}\n\n## Notes\n\nbody\n"
    assert parse_note(text, note_id="t").pinned is False


def test_store_set_pinned_persists_and_is_idempotent(tmp_path) -> None:
    store = NoteStore(path=tmp_path, clock=lambda: 100.0)
    store.update(NoteEntry(note_id="constraints", title="硬约束", content="接口必须 HTTPS"))
    assert store.get("constraints").pinned is False

    pinned = store.set_pinned("constraints", pinned=True)
    assert pinned.pinned is True
    assert pinned.updated_at == 100.0  # noqa: PLR2004 — 注入时钟常量
    raw = (tmp_path / "constraints.md").read_text(encoding="utf-8")
    assert "- pinned: true" in raw

    # 新实例读回（落盘真源）
    assert NoteStore(path=tmp_path).get("constraints").pinned is True

    # 幂等：同值再置 ⇒ 不写盘、不 bump updated_at
    store2 = NoteStore(path=tmp_path, clock=lambda: 999.0)
    again = store2.set_pinned("constraints", pinned=True)
    assert again.updated_at == 100.0, "同值重置不搅动时间戳"  # noqa: PLR2004 — 仍是首次时钟值
    assert (tmp_path / "constraints.md").read_text(encoding="utf-8") == raw

    # unpin ⇒ 行消失、渲染回到逐字
    store2.set_pinned("constraints", pinned=False)
    assert "- pinned" not in (tmp_path / "constraints.md").read_text(encoding="utf-8")
    assert store2.get("constraints").pinned is False


def test_store_set_pinned_missing_raises(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    with pytest.raises(NoteError) as excinfo:
        store.set_pinned("missing", pinned=True)
    assert excinfo.value.code is NoteErrorCode.NOTE_NOT_FOUND


def test_store_pinned_digest_carries_full_body(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    long_body = "硬约束：" + "必须" * 300  # 远超 _MAX_EXCERPT_CHARS(200)
    store.update(NoteEntry(note_id="constraints", title="硬约束", content=long_body, pinned=True))
    store.update(NoteEntry(note_id="other", title="其他", content="无关正文"))

    block = store.pinned_digest()
    assert long_body in block, "常驻注入完整正文（非节选）"
    assert "无关正文" not in block, "未标记笔记不进常驻块"
    assert long_body not in store.digest("硬约束"), "Consult 面仍只给 ≤200 节选（两通道互不交叉）"


def test_store_pinned_digest_empty_without_pins(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    store.update(NoteEntry(note_id="a", title="A", content="正文"))
    assert store.pinned_digest() == ""

    # 空正文的常驻笔记：仍在 pinned()，但不占块（避免每轮一个只有标题的空块）
    store.update(NoteEntry(note_id="b", title="B", content="   ", pinned=True))
    assert [note.note_id for note in store.pinned()] == ["b"]
    assert store.pinned_digest() == ""


def test_store_pinned_digest_is_deterministic_and_capped(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    store.update(NoteEntry(note_id="b", title="B", content="b-body", pinned=True))
    store.update(NoteEntry(note_id="a", title="A", content="a-body", pinned=True))
    block = store.pinned_digest()
    assert block.index("a-body") < block.index("b-body"), "按 note_id 升序（确定性）"

    store.update(NoteEntry(note_id="huge", title="Huge", content="x" * 10000, pinned=True))
    assert len(store.pinned_digest()) == _MAX_PINNED_CHARS, "总长有界（token 有界）"


def test_store_observe_turn_preserves_pinned(tmp_path) -> None:
    """逐轮写回（observe_turn）不得抹除常驻标记（否则常驻在长任务中途静默消失 —— E93 失效面）。"""
    store = NoteStore(path=tmp_path)
    store.update(NoteEntry(note_id="部署流程", title="部署流程", content="先备份", pinned=True))

    assert store.observe_turn("部署流程", ["滚动更新"], ok=True) is not None
    raw = (tmp_path / "部署流程.md").read_text(encoding="utf-8")
    assert "- pinned: true" in raw
    assert store.get("部署流程").pinned is True
