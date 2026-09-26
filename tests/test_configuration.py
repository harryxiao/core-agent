"""configuration 单元测试（对齐规格场景 + M0 验收）。

覆盖 spec/configuration 的场景：
- config.yaml 单一收口 + env 覆盖 + 缺省默认值
- LLM 必选校验阻断启动 / 完整正常启动
- feature flag 缺省关闭 / 开启初始化
- 密钥经 env/keychain 分级、yaml 拒绝明文、日志不泄露
- schema 校验通过才生效、半写回滚
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.configuration import (
    AppConfig,
    ConfigManager,
    ConfigurationError,
    LLMConfig,
    ValidationResult,
)
from core.plugin_registry import CoeffectResolver, EffectTracker

_VALID_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
features:
  voice_output: false
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _manager(tmp_path: Path, yaml: str, **kwargs) -> ConfigManager:
    path = _write(tmp_path / "config.yaml", yaml)
    environ = kwargs.pop("environ", None)
    if environ is None:
        environ = {"OPENAI_API_KEY": "sk-test"}
    else:
        environ = {"OPENAI_API_KEY": "sk-test", **environ}
    return ConfigManager(path, environ=environ, **kwargs)


def test_llm_missing_blocks_startup(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "llm:\n  provider: openai\n  model: gpt-4o\n",
    )
    with pytest.raises(ConfigurationError):
        manager.load()


def test_llm_complete_loads(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    config = manager.load()
    assert config.llm.provider == "openai"
    assert config.llm.api_key_ref == "${OPENAI_API_KEY}"  # 只存引用，不存明文


def test_env_overrides_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _VALID_YAML,
        environ={"OPENAI_API_KEY": "sk-test", "CORE_LLM_MODEL": "gpt-4o-mini"},
    )
    config = manager.load()
    assert config.llm.model == "gpt-4o-mini"


def test_feature_flag_default_off(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    manager.load()
    assert manager.is_enabled("voice_output") is False
    assert manager.is_enabled("nonexistent") is False


def test_feature_flag_on(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _VALID_YAML,
        environ={"OPENAI_API_KEY": "sk-test", "CORE_FEATURES_VOICE_OUTPUT": "true"},
    )
    manager.load()
    assert manager.is_enabled("voice_output") is True


def test_yaml_plaintext_secret_rejected(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "llm:\n  provider: openai\n  model: gpt-4o\n  endpoint: e\n  api_key: sk-RAW-PLAINTEXT\n",
    )
    with pytest.raises(ConfigurationError) as exc_info:
        manager.load()
    assert "sk-RAW-PLAINTEXT" not in str(exc_info.value)


def test_resolve_secret_from_env(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    manager.load()
    assert manager.resolve_secret("${OPENAI_API_KEY}") == "sk-test"


def test_resolve_secret_from_keychain(tmp_path: Path) -> None:
    keychain = CoeffectResolver()
    keychain.register("secret:IM_SECRET", "im-sk", secret=True)
    manager = ConfigManager(
        _write(tmp_path / "config.yaml", _VALID_YAML),
        environ={"OPENAI_API_KEY": "sk-test"},
        keychain=keychain,
    )
    manager.load()
    assert manager.resolve_secret("${IM_SECRET}") == "im-sk"


def test_validate_schema_reports_errors(tmp_path: Path) -> None:
    manager = ConfigManager(_write(tmp_path / "config.yaml", _VALID_YAML), environ={})
    config = AppConfig(llm=LLMConfig(provider="openai", model="", endpoint="", api_key_ref=""))
    result = manager.validate_schema(config)
    assert result.ok is False
    assert isinstance(result, ValidationResult)
    assert any("llm.model" in e for e in result.errors)


def test_apply_change_and_rollback(tmp_path: Path) -> None:
    effects = EffectTracker()
    manager = ConfigManager(
        _write(tmp_path / "config.yaml", _VALID_YAML),
        environ={"OPENAI_API_KEY": "sk-test"},
        effects=effects,
    )
    manager.load()
    config = manager.apply_change({"features": {"voice_output": True}})
    assert config.features["voice_output"] is True
    assert manager.is_enabled("voice_output") is True
    effects.rollback("config")
    assert manager.is_enabled("voice_output") is False


def test_apply_change_invalid_unchanged(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    manager.load()
    manager.apply_change({"features": {"voice_output": True}})
    assert manager.is_enabled("voice_output") is True
    with pytest.raises(ConfigurationError):
        manager.apply_change({"llm": {"api_key": "sk-BAD-PLAINTEXT"}})
    assert manager.is_enabled("voice_output") is True  # 失败不改变既有状态


def test_app_config_type(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    config = manager.load()
    assert isinstance(config, AppConfig)
