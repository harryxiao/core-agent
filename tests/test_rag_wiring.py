"""rag 主链路接线测试（change 0104）。

证明三件事：① 组合根装配后 `runtime.rag` 是**可用链路**（不再是无生产调用方的死代码）——
`build_runtime` → `RagService`，缺省 `HashEmbedder` 离线降级；② 端到端 ingest → search 命中 →
ask 生成（生成器经桩 provider，**不出网**）；③ CLI `rag ingest|search|ask` 三子命令驱动同一门面，
结构化错误（`INDEX_CORRUPT` / `GENERATION_UNAVAILABLE`）落 stderr 并给退出码 1。

状态目录由 conftest 的 `CORE_STATE_DIR` 隔离 ⇒ 两次 `main(...)` 是**两个装配周期**的语义，
跨进程复用（落盘索引 + 文档 content_hash）在此可测。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.configuration import ConfigManager
from core.entry import main
from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from core.rag import Chunk, HashEmbedder, RagService, SqliteVectorStore
from core.runtime import build_runtime


class _StubProvider(LLMProvider):
    """替代 `StdlibLLMProvider` 的桩：构造签名兼容组合根调用点，调用期不出网。"""

    def __init__(self, *, api_key: str = "", base_url: str | None = None, model: str = "") -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.last_request: LLMRequest | None = None

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse(
            content="接线答案",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest):
        yield LLMChunk(content="接线答案")

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


def _write_config(tmp_path, *, embedding_model: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    embed_line = f"  embedding_model: {embedding_model}\n" if embedding_model else ""
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n" + embed_line,
        encoding="utf-8",
    )
    return str(cfg)


def _index_path() -> Path:
    """CLI 与组合根共用的落盘索引路径（`$CORE_STATE_DIR/rag-index.db`）。"""
    return Path(os.environ["CORE_STATE_DIR"]) / "rag-index.db"


@pytest.fixture
def offline(monkeypatch) -> None:
    """组合根构造的 provider 换成桩：装配全过程与调用期均不出网。"""
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _StubProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


# ---- 组合根装配 + 端到端 ----


def test_build_runtime_wires_rag_service(offline, tmp_path) -> None:
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert isinstance(runtime.rag, RagService)
    assert runtime.rag.ingest("d1", "部署流程说明") == 1  # noqa: PLR2004
    assert runtime.rag.search("部署流程")[0].chunk.doc_id == "d1"


def test_runtime_rag_end_to_end_ingest_search_ask(offline, tmp_path) -> None:
    """端到端：ingest → search 命中 → ask 生成（检索片段注入提示词），全程离线。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert runtime.rag.ingest("kb#1", "部署流程：先构建镜像，再滚动发布") > 0
    hits = runtime.rag.search("如何部署", top_k=3)
    assert hits and hits[0].chunk.doc_id == "kb#1"

    assert runtime.rag.ask("如何部署") == "接线答案"
    provider = runtime.llm
    assert isinstance(provider, _StubProvider)
    assert provider.last_request is not None
    assert "滚动发布" in provider.last_request.messages[0].content, "检索片段注入生成提示词"


def test_runtime_rag_degrades_to_offline_embedder(offline, tmp_path) -> None:
    """未配 `llm.embedding_model` ⇒ 离线 `HashEmbedder` 降级基线（组合根不构造语义 provider）。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert runtime.rag.embedder_name == "HashEmbedder"


# ---- CLI 三子命令 ----


def test_cli_rag_ingest_then_search_across_assemblies(offline, tmp_path, capsys) -> None:
    """两次 `main(...)`（两次装配）：摄取成果与文档指纹在后续装配中可见。"""
    cfg = _write_config(tmp_path)
    doc = tmp_path / "kb.md"
    doc.write_text("部署流程说明：先构建镜像，再滚动发布", encoding="utf-8")

    assert main(["--config", cfg, "rag", "ingest", str(doc), "--doc-id", "d1"]) == 0
    first = capsys.readouterr()
    assert "d1" in first.out
    assert "HashEmbedder" in first.err, "离线降级提示落 stderr（不污染 stdout 机读输出）"

    assert main(["--config", cfg, "rag", "ingest", str(doc), "--doc-id", "d1"]) == 0
    assert "无变更" in capsys.readouterr().out, "同一内容重复摄取按 content_hash 判定为无变更"

    assert main(["--config", cfg, "rag", "search", "部署流程", "--top-k", "2"]) == 0
    searched = capsys.readouterr().out
    assert "d1#0" in searched and "d1" in searched


def test_cli_rag_ask_prints_answer(offline, tmp_path, capsys) -> None:
    """`rag ask` 走检索增强生成，打印答案。"""
    cfg = _write_config(tmp_path)
    doc = tmp_path / "kb.md"
    doc.write_text("部署流程说明", encoding="utf-8")
    assert main(["--config", cfg, "rag", "ingest", str(doc), "--doc-id", "d1"]) == 0
    capsys.readouterr()

    assert main(["--config", cfg, "rag", "ask", "如何部署"]) == 0
    assert "接线答案" in capsys.readouterr().out


def test_cli_rag_ask_without_generator_fails_closed(monkeypatch, capsys) -> None:
    """生成器缺失（服务层未装配）⇒ 结构化错误 + 退出码 1，不静默给空答案。"""
    service = RagService(HashEmbedder(), SqliteVectorStore(_index_path()))
    monkeypatch.setattr("core.entry.build_runtime", lambda *_a, **_kw: SimpleNamespace(rag=service))

    assert main(["rag", "ask", "问题"]) == 1
    assert "GENERATION_UNAVAILABLE" in capsys.readouterr().err


def test_cli_rag_search_rejects_dim_mismatch_with_hint(offline, capsys) -> None:
    """索引维度与当前 embedding 不一致 ⇒ 结构化错误 + 「重建索引」提示 + 退出码 1。"""
    store = SqliteVectorStore(_index_path())
    store.put(Chunk("c1", "d1", "旧索引", [1.0, 0.0]))

    assert main(["rag", "search", "部署"]) == 1
    err = capsys.readouterr().err
    assert "INDEX_CORRUPT" in err
    assert "重建索引" in err
