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

from core.configuration import ConfigManager, config_specs
from core.context import InfoMap
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
from core.runtime import _RAG_INFO_MAP_MAX_DOCS, _index_rag_docs, build_runtime


class _StubProvider(LLMProvider):
    """替代 `StdlibLLMProvider` 的桩：构造签名兼容组合根调用点，调用期不出网。"""

    def __init__(  # noqa: PLR0913 — 桩镜像 provider 构造签名
        self,
        *,
        api_key: str = "",
        base_url: str | None = None,
        model: str = "",
        provider: str = "",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
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


def _write_config(tmp_path, *, embedding_model: str = "", extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    embed_line = f"  embedding_model: {embedding_model}\n" if embedding_model else ""
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n" + embed_line + extra,
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


def test_cli_rag_search_rejects_dim_mismatch_with_hint(offline, tmp_path, capsys) -> None:
    """索引维度与当前 embedding 不一致 ⇒ 结构化错误 + 「重建索引」提示 + 退出码 1。"""
    store = SqliteVectorStore(_index_path())
    store.put(Chunk("c1", "d1", "旧索引", [1.0, 0.0]))
    # 显式钉住未知端点 ⇒ HashEmbedder（change 0271 后默认配置可能按端点推导语义后端，
    # 维度失配用例不应依赖用户 HOME 下的配置内容）。
    cfg = _write_config(tmp_path)

    assert main(["--config", cfg, "rag", "search", "部署"]) == 1
    err = capsys.readouterr().err
    assert "INDEX_CORRUPT" in err
    assert "重建索引" in err


# ---- InfoMap × rag（change 0210 / ADR-0200）----

_FLAG_ON = "context:\n  rag_info_map: true\n"
_DOC_12 = "abcdefghijkl"  # 12 字符 ⇒ chunk_size=1 ⇒ 块 id `d#0`…`d#11`


def _seed(store: SqliteVectorStore, doc_id: str, content: str) -> None:
    RagService(HashEmbedder(), store, chunk_size=64).ingest(doc_id, content)


def _rag_pointer_doc_ids(runtime) -> set[str]:
    """装配器目录层里的文档 id 集合（经主 loop 的真 planner 取装配器）。"""
    assembler = runtime.loop._planner._assembler  # noqa: SLF001
    return {p["doc_id"] for p in assembler.build("部署", "reason", budget=2048).pointers}


def test_chunk_texts_reconstructs_source_in_chunk_order() -> None:
    """>10 块按**块序号**拼回 == 原文 —— 按 `chunk_id` 字典序拼会踩 `#10 < #2` 错序。"""
    store = SqliteVectorStore(_index_path())
    RagService(HashEmbedder(), store, chunk_size=1).ingest("d", _DOC_12)

    assert store.document_ids() == ["d"]
    assert "".join(store.chunk_texts("d")) == _DOC_12  # 字典序 ⇒ "abklcdefghij" ≠ 原文


def test_vector_store_accessors_are_fail_soft_on_empty() -> None:
    """空库 ⇒ 两访问器返空（不抛）；未登记的 doc_id ⇒ 块文本空。"""
    store = SqliteVectorStore(_index_path())
    assert store.document_ids() == []
    assert store.chunk_texts("absent") == []


def test_index_rag_docs_caps_documents_and_skips_core_profile() -> None:
    """20 档 ⇒ 只上限个进地图；`core-profile` 跳过（真源已由 profile 分支建索引）。"""
    store = SqliteVectorStore(_index_path())
    for i in range(20):
        _seed(store, f"doc{i:02d}", f"# 标题{i}\n内容{i}")
    _seed(store, "core-profile", "# 顶\n真源")

    info_map = InfoMap()
    _index_rag_docs(info_map, store)

    docs = info_map.documents()
    assert "core-profile" not in docs
    assert len(docs) == _RAG_INFO_MAP_MAX_DOCS  # noqa: PLR2004 — 上限是硬约束


def test_spec_declares_rag_info_map_key() -> None:
    specs = {spec.key: spec for spec in config_specs()}
    assert "context.rag_info_map" in specs


def test_rag_info_map_flag_on_indexes_rag_documents(offline, tmp_path) -> None:
    """旗开 ⇒ 目录层 `pointers` 含 rag 库文档（从块拼回原文上建目录索引）。"""
    _seed(SqliteVectorStore(_index_path()), "kb-deploy", "# 部署\n先构建镜像，再滚动发布")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, extra=_FLAG_ON)))

    assert "kb-deploy" in _rag_pointer_doc_ids(runtime)


def test_rag_info_map_flag_off_leaves_catalog_unchanged(offline, tmp_path) -> None:
    """缺省关（零回归锚）⇒ rag 文档**不进**目录层。"""
    _seed(SqliteVectorStore(_index_path()), "kb-deploy", "# 部署\n先构建镜像，再滚动发布")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert "kb-deploy" not in _rag_pointer_doc_ids(runtime)


def test_rag_info_map_illegal_value_normalizes_to_off(offline, tmp_path) -> None:
    """`context` 非结构化段 ⇒ 集合外取值归一为**关闭**（不阻断启动）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, extra="context:\n  rag_info_map: maybe\n"))
    )
    assert runtime.config.rag_info_map() is False
