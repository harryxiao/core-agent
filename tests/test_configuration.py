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
    ConfigSpec,
    ConfigurationError,
    JudgmentConfig,
    LLMConfig,
    PetConfig,
    ValidationResult,
    generate_cli_flags,
    generate_env_vars,
    generate_yaml_defaults,
    resolve,
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


def test_write_patch_round_trips(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    manager.load()
    manager.write_patch({"llm": {"model": "gpt-4.1"}})
    # 新进程（新实例）读回：model 已更新，api_key 引用与未触及键原样保留
    reloaded = ConfigManager(tmp_path / "config.yaml", environ={"OPENAI_API_KEY": "sk-test"})
    config = reloaded.load()
    assert config.llm.model == "gpt-4.1"
    assert config.llm.api_key_ref == "${OPENAI_API_KEY}"
    assert config.features == {"voice_output": False}


def test_write_patch_rejects_plaintext_via_apply(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    manager.load()
    with pytest.raises(ConfigurationError):
        manager.apply_change({"llm": {"api_key": "sk-BAD-PLAINTEXT"}})
    # apply_change 拒绝明文密钥，写回不会发生（文件未被篡改）
    reloaded = ConfigManager(tmp_path / "config.yaml", environ={"OPENAI_API_KEY": "sk-test"})
    assert reloaded.load().llm.api_key_ref == "${OPENAI_API_KEY}"


# ---- M5：ConfigSpec 单一真源 + CLI 覆盖层 ----


def test_resolve_priority_chain() -> None:
    specs = [
        ConfigSpec(
            "llm.model",
            "--llm.model",
            "CORE_LLM_MODEL",
            default="default-model",
            map_to="llm.model",
        ),
    ]
    assert (
        resolve(
            "llm.model",
            cli={"llm.model": "from-cli"},
            env={"CORE_LLM_MODEL": "from-env"},
            yaml={"llm.model": "from-yaml"},
            specs=specs,
        )
        == "from-cli"
    )
    assert (
        resolve(
            "llm.model",
            env={"CORE_LLM_MODEL": "from-env"},
            yaml={"llm.model": "from-yaml"},
            specs=specs,
        )
        == "from-env"
    )
    assert resolve("llm.model", yaml={"llm.model": "from-yaml"}, specs=specs) == "from-yaml"
    assert resolve("llm.model", specs=specs) == "default-model"


def test_config_spec_three_faces_consistent() -> None:
    specs = [
        ConfigSpec("llm.model", "--llm.model", "CORE_LLM_MODEL", default="", map_to="llm.model"),
        ConfigSpec(
            "permission.mode",
            "--permission-mode",
            "CORE_PERMISSION_MODE",
            default="interactive",
            map_to="permission.mode",
        ),
    ]
    assert generate_cli_flags(specs) == ["--llm.model", "--permission-mode"]
    assert generate_env_vars(specs) == ["CORE_LLM_MODEL", "CORE_PERMISSION_MODE"]
    assert generate_yaml_defaults(specs) == {"llm.model": "", "permission.mode": "interactive"}


def test_invalid_map_to_blocks_startup(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _VALID_YAML,
        specs=[ConfigSpec("bad", "--bad", "CORE_BAD", default="", map_to="")],
    )
    with pytest.raises(ConfigurationError):
        manager.load()


def test_duplicate_map_to_blocks_startup(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _VALID_YAML,
        specs=[
            ConfigSpec("a", "--a", "CORE_A", default="", map_to="llm.model"),
            ConfigSpec("b", "--b", "CORE_B", default="", map_to="llm.model"),
        ],
    )
    with pytest.raises(ConfigurationError):
        manager.load()


def test_cli_overrides_env_and_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _VALID_YAML,
        environ={"OPENAI_API_KEY": "sk-test", "CORE_LLM_MODEL": "gpt-4o-mini"},
        cli={"llm.model": "from-cli"},
    )
    config = manager.load()
    assert config.llm.model == "from-cli"


def test_permission_mode_from_config(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML, cli={"permission.mode": "read-only"})
    manager.load()
    assert manager.permission_mode() == "read-only"


def test_permission_mode_default(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    manager.load()
    assert manager.permission_mode() == "interactive"


# ---- M6：pet.* ConfigSpec 单一真源 ----


_PET_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
pet:
  enabled: true
  persons_dir: ./pets
"""


def test_pet_config_resolve_defaults() -> None:
    assert resolve("pet.enabled") is False
    assert resolve("pet.persons_dir") == "persons"


def test_pet_config_from_yaml(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _PET_YAML)
    config = manager.load()
    assert config.pet == PetConfig(enabled=True, persons_dir="./pets")


def test_pet_config_absent(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    assert manager.load().pet is None


def test_pet_enabled_env_override(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _PET_YAML,
        environ={"OPENAI_API_KEY": "sk-test", "CORE_PET_ENABLED": "false"},
    )
    config = manager.load()
    assert config.pet is not None
    assert config.pet.enabled is False


# ---- M8：judgment.* ConfigSpec 单一真源 ----


_JUDGMENT_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
judgment:
  provider: jev
  model: systemone
  base_url: http://jev.local
  api_key: ${JEV_API_KEY}
  confidence_threshold: 0.8
"""


def test_judgment_config_resolve_defaults() -> None:
    assert resolve("judgment.provider") == ""
    assert resolve("judgment.confidence_threshold") == 0.7  # noqa: PLR2004


def test_judgment_config_from_yaml(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _JUDGMENT_YAML, environ={"JEV_API_KEY": "jev-sk"})
    config = manager.load()
    assert config.judgment == JudgmentConfig(
        provider="jev",
        model="systemone",
        base_url="http://jev.local",
        api_key_ref="${JEV_API_KEY}",
        confidence_threshold=0.8,
    )


def test_judgment_config_absent(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    assert manager.load().judgment is None


def test_judgment_env_override(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _JUDGMENT_YAML,
        environ={"JEV_API_KEY": "jev-sk", "CORE_JUDGMENT_MODEL": "systemone-mini"},
    )
    config = manager.load()
    assert config.judgment is not None
    assert config.judgment.model == "systemone-mini"


def test_judgment_plaintext_secret_rejected(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "llm:\n  provider: openai\n  model: gpt-4o\n  endpoint: e\n  api_key: ${OPENAI_API_KEY}\n"
        "judgment:\n  provider: jev\n  api_key: sk-RAW-JEV\n",
    )
    with pytest.raises(ConfigurationError) as exc_info:
        manager.load()
    assert "judgment.api_key" in str(exc_info.value)
    assert "sk-RAW-JEV" not in str(exc_info.value)
