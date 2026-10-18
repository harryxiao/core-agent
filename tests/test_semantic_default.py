"""语义检索默认化（change 0271 / ADR-0261）：端点推导表 / 有效配置 / 接线 / 提示。"""

from __future__ import annotations

import pytest

from core.configuration import ConfigurationError
from core.configuration.embedding_models import default_embedding_model
from core.configuration.manager import ConfigManager
from core.configuration.models import LLMConfig
from core.llm_provider import Embedding, LLMError
from core.memory import MemoryEntry
from core.runtime import build_runtime

_ENV = {"OPENAI_API_KEY": "sk-test"}


def _llm(
    endpoint: str,
    *,
    embedding_model: str = "",
    embedding_auto: bool = True,
    embedding_required: bool = False,
) -> LLMConfig:
    return LLMConfig(
        provider="zai",
        model="glm-5.3",
        endpoint=endpoint,
        api_key_ref="${K}",
        embedding_model=embedding_model,
        embedding_auto=embedding_auto,
        embedding_required=embedding_required,
    )


# ---- 端点表 ----


def test_endpoint_table_matches_known_hosts() -> None:
    assert default_embedding_model("https://api.openai.com/v1") == "text-embedding-3-small"
    assert default_embedding_model("https://open.bigmodel.cn/api/paas/v4") == "embedding-3"
    assert (
        default_embedding_model("https://dashscope.aliyuncs.com/compatible-mode/v1")
        == "text-embedding-v3"
    )
    assert default_embedding_model("https://api.siliconflow.cn/v1") == "BAAI/bge-m3"


def test_endpoint_table_is_case_insensitive_and_scheme_optional() -> None:
    assert default_embedding_model("HTTPS://API.OPENAI.COM/v1") == "text-embedding-3-small"
    assert default_embedding_model("api.openai.com/v1") == "text-embedding-3-small"
    assert default_embedding_model("api.openai.com:443/v1") == "text-embedding-3-small"


def test_endpoint_table_matches_subdomains() -> None:
    assert default_embedding_model("https://edge.api.openai.com/v1") == "text-embedding-3-small"


def test_endpoint_table_unknown_or_empty_returns_empty() -> None:
    assert default_embedding_model("") == ""
    assert default_embedding_model("   ") == ""
    assert default_embedding_model("https://example.com/v1") == ""
    assert default_embedding_model("https://api.deepseek.com/v1") == ""
    assert default_embedding_model("http://127.0.0.1:8000/v1") == ""


def test_endpoint_table_does_not_match_suffix_without_dot_boundary() -> None:
    assert default_embedding_model("https://evilopen.bigmodel.cn.attacker.test/v1") == ""


# ---- 有效配置 ----


def test_effective_model_derives_from_endpoint_by_default() -> None:
    llm = _llm("https://open.bigmodel.cn/api/paas/v4")

    assert llm.embedding_model == ""  # 字段仍是用户显式值
    assert llm.effective_embedding_model == "embedding-3"


def test_effective_model_explicit_wins_over_derivation() -> None:
    llm = _llm("https://open.bigmodel.cn/api/paas/v4", embedding_model="custom-embed")

    assert llm.effective_embedding_model == "custom-embed"


def test_effective_model_disabled_by_switch() -> None:
    llm = _llm("https://open.bigmodel.cn/api/paas/v4", embedding_auto=False)

    assert llm.effective_embedding_model == ""


def test_effective_model_explicit_survives_disabled_switch() -> None:
    llm = _llm(
        "https://open.bigmodel.cn/api/paas/v4",
        embedding_model="custom-embed",
        embedding_auto=False,
    )

    assert llm.effective_embedding_model == "custom-embed"


def test_effective_model_unknown_endpoint_is_empty() -> None:
    assert _llm("https://example.com/v1").effective_embedding_model == ""


# ---- 配置三面 ----


def _write_config(tmp_path, llm_block: str) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: zai\n"
        "  model: glm-5.3\n"
        "  endpoint: https://open.bigmodel.cn/api/paas/v4\n"
        "  api_key: ${OPENAI_API_KEY}\n" + llm_block,
        encoding="utf-8",
    )
    return str(cfg)


def test_config_embedding_auto_defaults_true(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(yaml_path=_write_config(tmp_path, ""), environ=_ENV)

    config = manager.load()

    assert config.llm.embedding_auto is True
    assert config.llm.effective_embedding_model == "embedding-3"


def test_config_embedding_auto_from_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, "  embedding_auto: false\n"), environ=_ENV
    )

    config = manager.load()

    assert config.llm.embedding_auto is False
    assert config.llm.effective_embedding_model == ""


def test_config_embedding_auto_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, ""),
        environ={**_ENV, "CORE_LLM_EMBEDDING_AUTO": "off"},
    )

    assert manager.load().llm.embedding_auto is False


def test_config_embedding_auto_from_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, ""),
        environ=_ENV,
        cli={"llm.embedding_auto": "0"},
    )

    assert manager.load().llm.embedding_auto is False


def test_config_embedding_auto_invalid_blocks_startup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, "  embedding_auto: maybe\n"), environ=_ENV
    )

    with pytest.raises(ConfigurationError, match="embedding_auto"):
        manager.load()


# ---- embedding_required（change 0289） ----


def _write_config_at(tmp_path, endpoint: str, llm_block: str) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: zai\n"
        "  model: glm-5.3\n"
        f"  endpoint: {endpoint}\n"
        "  api_key: ${OPENAI_API_KEY}\n" + llm_block,
        encoding="utf-8",
    )
    return str(cfg)


def test_config_embedding_required_defaults_false(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(yaml_path=_write_config(tmp_path, ""), environ=_ENV)

    assert manager.load().llm.embedding_required is False


def test_config_embedding_required_from_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, "  embedding_required: true\n"), environ=_ENV
    )

    assert manager.load().llm.embedding_required is True


def test_config_embedding_required_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, ""),
        environ={**_ENV, "CORE_LLM_EMBEDDING_REQUIRED": "yes"},
    )

    assert manager.load().llm.embedding_required is True


def test_config_embedding_required_from_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, ""),
        environ=_ENV,
        cli={"llm.embedding_required": "1"},
    )

    assert manager.load().llm.embedding_required is True


def test_config_embedding_required_invalid_blocks_startup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, "  embedding_required: maybe\n"), environ=_ENV
    )

    with pytest.raises(ConfigurationError, match="embedding_required"):
        manager.load()


def test_embedding_required_blocks_startup_when_effective_model_empty(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config_at(
            tmp_path, "https://example.com/v1", "  embedding_required: true\n"
        ),
        environ=_ENV,
    )

    with pytest.raises(ConfigurationError) as excinfo:
        manager.load()

    message = str(excinfo.value)
    assert "embedding_required" in message
    assert "example.com" not in message  # 不回显端点（更不回显密钥）


def test_embedding_required_accepts_explicit_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config_at(
            tmp_path,
            "https://example.com/v1",
            "  embedding_model: custom-embed\n  embedding_required: true\n",
        ),
        environ=_ENV,
    )

    config = manager.load()

    assert config.llm.effective_embedding_model == "custom-embed"


def test_embedding_required_accepts_derived_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, "  embedding_required: true\n"), environ=_ENV
    )

    assert manager.load().llm.effective_embedding_model == "embedding-3"


def test_embedding_required_off_keeps_lexical_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config_at(tmp_path, "https://example.com/v1", ""), environ=_ENV
    )

    assert manager.load().llm.effective_embedding_model == ""


def test_embedding_required_hot_update_to_empty_model_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, "  embedding_required: true\n"), environ=_ENV
    )
    manager.load()

    with pytest.raises(ConfigurationError, match="embedding_required"):
        manager.apply_change({"llm": {"endpoint": "https://example.com/v1"}})


def test_hot_update_keeps_explicit_field_and_follows_endpoint(tmp_path, monkeypatch) -> None:
    """推导值不固化：换端点后有效模型跟随，字段仍是空串（用户未显式声明）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    manager = ConfigManager(yaml_path=_write_config(tmp_path, ""), environ=_ENV)
    manager.load()

    updated = manager.apply_change({"llm": {"endpoint": "https://api.openai.com/v1"}})

    assert updated.llm.embedding_model == ""
    assert updated.llm.effective_embedding_model == "text-embedding-3-small"


# ---- 组合根接线 ----


def _fake_provider_cls(constructed: list[tuple[str, str | None]]):
    class _FakeProvider:
        def __init__(  # noqa: PLR0913 — 桩镜像 provider 构造签名
            self,
            *,
            api_key: str,
            base_url: str | None,
            model: str,
            provider: str = "",
            timeout: float = 60.0,
            max_retries: int = 3,
        ) -> None:
            constructed.append((model, base_url))

        def embedding(self, texts: list[str]) -> list[Embedding]:
            return [Embedding(vector=[float(len(t))]) for t in texts]

    return _FakeProvider


def _build(
    tmp_path, monkeypatch, llm_block: str = ""
) -> tuple[object, list[tuple[str, str | None]]]:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    constructed: list[tuple[str, str | None]] = []
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _fake_provider_cls(constructed))
    runtime = build_runtime(
        ConfigManager(
            yaml_path=_write_config(tmp_path, llm_block),
            environ=_ENV,
        )
    )
    return runtime, constructed


def test_runtime_derives_embedder_for_known_endpoint(tmp_path, monkeypatch) -> None:
    runtime, constructed = _build(tmp_path, monkeypatch)

    assert ("embedding-3", "https://open.bigmodel.cn/api/paas/v4") in constructed
    embedder = runtime.memory._embedder
    assert embedder is not None
    assert embedder(["ab", "cde"]) == [[2.0], [3.0]]
    assert runtime.rag.embedder_name == "LLMEmbedder"


def test_runtime_respects_embedding_auto_false(tmp_path, monkeypatch) -> None:
    runtime, constructed = _build(tmp_path, monkeypatch, "  embedding_auto: false\n")

    assert ("embedding-3", "https://open.bigmodel.cn/api/paas/v4") not in constructed
    assert runtime.memory._embedder is None
    assert runtime.rag.embedder_name == "HashEmbedder"


def test_runtime_explicit_model_wins(tmp_path, monkeypatch) -> None:
    runtime, constructed = _build(tmp_path, monkeypatch, "  embedding_model: custom-embed\n")

    assert ("custom-embed", "https://open.bigmodel.cn/api/paas/v4") in constructed
    assert ("embedding-3", "https://open.bigmodel.cn/api/paas/v4") not in constructed
    assert runtime.memory._embedder is not None


def test_runtime_unknown_endpoint_keeps_lexical(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: custom\n"
        "  model: m\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )

    runtime = build_runtime(ConfigManager(yaml_path=str(cfg), environ=_ENV))

    assert runtime.memory._embedder is None
    assert runtime.rag.embedder_name == "HashEmbedder"


def test_runtime_derivation_failure_degrades_without_blocking(tmp_path, monkeypatch) -> None:
    """推导模型不可达：启动不阻断，首次 embed 失败后记忆降级词法（既有短路口径）。"""

    class _FailingProvider:
        def __init__(self, **kwargs: object) -> None:
            pass

        def embedding(self, texts: list[str]) -> list[Embedding]:
            raise LLMError("embedding unreachable")  # noqa: TRY003 — 模拟端点不可达

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _FailingProvider)

    runtime = build_runtime(
        ConfigManager(
            yaml_path=_write_config(tmp_path, ""),
            environ=_ENV,
        )
    )

    assert runtime.memory._embedder is not None
    runtime.memory.write(
        "L2",
        MemoryEntry(id="m1", layer="L2", content="部署流程", tags=[], source="loop", trace_id="t1"),
    )
    assert [h.id for h in runtime.memory.read("部署")] == ["m1"]
