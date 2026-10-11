"""文档→摘要：`rag ingest --summarize` → `notes.rag` 结论笔记（change 0213 / 台账 E150）。

规格 `rag`「文档摄取与分块」要求：摄取 SHALL 支持**可选** `--summarize`，显式给出时把文档全文交给
一次模型调用产出摘要、落 canonical 结论笔记；未给该旗 ⇒ 既有摄取行为**逐字不变**、零笔记。
规格 `notes`「文档摘要笔记」要求：`source="notes.rag"`、`pinned=False`、幂等覆盖、**双守护**
（不被逐轮写回 / 提升覆写）、**进 digest 命中节选**（不入 `_ARCHIVE_SOURCES`）。本文件证明五件事：

- CLI `--summarize` ⇒ 产生一篇 `notes.rag` 结论笔记（source / tags / pinned 正确），无旗 ⇒ 零笔记；
- `_doc_summary_note` 幂等覆盖（同 `doc_id` ⇒ 单篇、刷新）、空 slug 守卫不写盘；
- 双守护：`observe_turn` 撞名回落 `<id>-2`、提升走独立命名空间 ⇒ 摘要笔记逐字不变；
- digest **命中节选**含摘要（结论层在推理上下文可见）。

全程离线（模型面为桩 provider，不出网）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from core.entry import _SUMMARY_NOTE_SOURCE, _doc_summary_note, main
from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from core.memory import MemoryEntry
from core.notes import NoteEntry, NoteStore, promote_session_summary

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)
_SUMMARY_REPLY = "接线答案"


class _StubProvider(LLMProvider):
    """替代 `StdlibLLMProvider` 的桩：构造签名兼容组合根调用点，调用期不出网。"""

    def __init__(self, **_kwargs: Any) -> None: ...

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=_SUMMARY_REPLY,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest):
        yield LLMChunk(content=_SUMMARY_REPLY)

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _StubProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _write_config(tmp_path: Path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    return str(cfg)


def _doc(tmp_path: Path, body: str = "部署流程：先构建镜像，再滚动发布") -> Path:
    path = tmp_path / "doc.md"
    path.write_text(body, encoding="utf-8")
    return path


def _notes_dir() -> Path:
    return Path(os.environ["CORE_STATE_DIR"]) / "notes"


def _summary_entry(session_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=f"compaction.summary.{session_id}",
        layer="L2",
        content=content,
        tags=["compaction", "summary"],
        source="compaction",
        trace_id=f"compaction.{session_id}",
        session_id=session_id,
        kind="semantic",
    )


# ---- 1. _doc_summary_note 基本语义 ----

# 桩 provider 产出的摘要正文（与组合根 `_SUMMARY_REPLY` 同款），用于「摘要进了笔记正文」断言。
_QUANT = "量化结论：风险中性"


def test_doc_summary_note_creates_conclusion_note(tmp_path: Path) -> None:
    """落盘真源（新实例读回）：source / tags / pinned 正确，正文含摘要。"""
    store = NoteStore(path=tmp_path)

    note = _doc_summary_note(store, doc_id="d1", summary=_QUANT)

    assert note is not None and note.note_id == "doc-d1"
    reloaded = NoteStore(path=tmp_path).get("doc-d1")
    assert reloaded.source == _SUMMARY_NOTE_SOURCE == "notes.rag"
    assert {"rag", "doc:d1", "summary"}.issubset(set(reloaded.tags))
    assert reloaded.pinned is False, "结论笔记不占常驻预算"
    assert _QUANT in reloaded.content


def test_doc_summary_note_is_idempotent_overwrite(tmp_path: Path) -> None:
    """同 `doc_id` 重复落摘要 ⇒ 命中**同一** note、覆盖刷新、不增长。"""
    NoteStore(path=tmp_path).update(
        NoteEntry(note_id="doc-d1", title="旧", content="旧正文", source=_SUMMARY_NOTE_SOURCE)
    )
    store = NoteStore(path=tmp_path)

    note = _doc_summary_note(store, doc_id="d1", summary="新结论")

    assert note is not None and note.note_id == "doc-d1"
    notes = [n for n in NoteStore(path=tmp_path).list() if n.note_id.startswith("doc-")]
    assert len(notes) == 1, "重摄取 ⇒ 单篇，不增长"
    assert "新结论" in notes[0].content, "覆盖式：内容为最新摘要"


def test_doc_summary_note_empty_slug_returns_none(tmp_path: Path) -> None:
    """`doc_id` 无可派生 slug ⇒ 返回 `None`、不写盘（与 `promote_session_summary` 同口径）。"""
    store = NoteStore(path=tmp_path)

    result = _doc_summary_note(store, doc_id="...", summary="x")

    assert result is None, "无可派生 slug ⇒ 不写盘"
    assert list(tmp_path.glob("*.md")) == [], "不产生任何 canonical 文件"


# ---- 2. 双守护：摘要笔记不被逐轮写回 / 提升覆写 ----


def test_doc_summary_note_survives_turn_writeback(tmp_path: Path) -> None:
    """`observe_turn` 撞上 `notes.rag` 笔记 ⇒ 走 `<id>-2` 回落，摘要笔记**逐字不变**。"""
    store = NoteStore(path=tmp_path)
    _doc_summary_note(store, doc_id="deploy", summary="发布流程结论")

    store.observe_turn("doc-deploy", ["tools.file_patch（path=c）→ 改配置"], ok=True)

    doc = store.get("doc-deploy")
    assert doc.source == _SUMMARY_NOTE_SOURCE and "发布流程结论" in doc.content, "摘要笔记未被覆写"
    assert store.get("doc-deploy-2") is not None, "逐轮沉淀改道派生主题"


def test_doc_summary_note_untouched_by_promotion(tmp_path: Path) -> None:
    """提升走 `session-` 命名空间 ⇒ 与 `doc-` 摘要笔记互不触碰。"""
    store = NoteStore(path=tmp_path)
    _doc_summary_note(store, doc_id="deploy", summary="发布流程结论")

    promote_session_summary(store, _summary_entry("deploy", "会话摘要"), session_id="deploy")

    doc = store.get("doc-deploy")
    assert doc.source == _SUMMARY_NOTE_SOURCE, "摘要笔记来源不变"
    assert store.get("session-deploy") is not None, "提升落自己的命名空间"


# ---- 3. digest 命中节选（结论层可见） ----


def test_doc_summary_note_enters_digest_excerpt(tmp_path: Path) -> None:
    """`notes.rag` 不属 `_ARCHIVE_SOURCES` ⇒ 进「命中的笔记」**节选**块（非仅清单）。"""
    store = NoteStore(path=tmp_path)
    _doc_summary_note(store, doc_id="risk", summary="量化结论：风险中性定价")

    digest = store.digest("量化结论")

    assert "命中的笔记：" in digest, "进命中节选面（而非仅清单标题）"
    assert "风险中性定价" in digest


# ---- 4. CLI 端到端 ----


def test_cli_ingest_summarize_writes_note(
    offline, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`rag ingest --summarize` ⇒ 摄取成功 + 落一篇 `notes.rag` 结论笔记（桩摘要正文）。"""
    cfg = _write_config(tmp_path)

    assert (
        main(
            ["--config", cfg, "rag", "ingest", str(_doc(tmp_path)), "--doc-id", "d1", "--summarize"]
        )
        == 0
    )

    note = NoteStore(path=_notes_dir()).get("doc-d1")
    assert note is not None, "带 --summarize ⇒ 产生结论笔记"
    assert note.source == _SUMMARY_NOTE_SOURCE
    assert _SUMMARY_REPLY in note.content, "摘要正文落进笔记"


def test_cli_ingest_without_summarize_writes_no_note(
    offline, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """无 `--summarize` ⇒ 零笔记（既有摄取行为逐字不变，零回归锚）。"""
    cfg = _write_config(tmp_path)

    assert main(["--config", cfg, "rag", "ingest", str(_doc(tmp_path)), "--doc-id", "d1"]) == 0

    assert NoteStore(path=_notes_dir()).list() == [], "无旗 ⇒ 不落任何 canonical 笔记"
