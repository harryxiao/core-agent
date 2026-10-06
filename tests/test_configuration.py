"""configuration 单元测试（对齐规格场景 + M0 验收）。

覆盖 spec/configuration 的场景：
- config.yaml 单一收口 + env 覆盖 + 缺省默认值
- LLM 必选校验阻断启动 / 完整正常启动
- feature flag 缺省关闭 / 开启初始化
- 密钥经 env/keychain 分级、yaml 拒绝明文、日志不泄露
- schema 校验通过才生效、半写回滚
"""

from __future__ import annotations

import os
import warnings
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


# ---- 思考回显开关（change 0145 / ADR-0137，账本 E60 开关面）----


def _yaml_with_show_thinking(raw: str) -> str:
    """把 `show_thinking` 插进 llm 段（`_VALID_YAML` 末尾已是 features 段）。"""
    anchor = "  api_key: ${OPENAI_API_KEY}\n"
    return _VALID_YAML.replace(anchor, anchor + f"  show_thinking: {raw}\n")


def test_show_thinking_default_off(tmp_path: Path) -> None:
    """缺省：`llm.show_thinking` 为**关**（既有配置逐字可载，行为零回归）。"""
    assert _manager(tmp_path, _VALID_YAML).load().llm.show_thinking is False


def test_show_thinking_native_bool(tmp_path: Path) -> None:
    """原生布尔直取，不经验证期改写。"""
    assert _manager(tmp_path, _yaml_with_show_thinking("true")).load().llm.show_thinking is True
    assert _manager(tmp_path, _yaml_with_show_thinking("false")).load().llm.show_thinking is False


@pytest.mark.parametrize("raw", ["true", "yes", "on", "1", "TRUE", " On "])
def test_show_thinking_truthy_set(tmp_path: Path, raw: str) -> None:
    """真值集合（含大小写与首尾空白变体）归一为**开**（与 feature flag 同集）。"""
    assert _manager(tmp_path, _yaml_with_show_thinking(raw)).load().llm.show_thinking is True


@pytest.mark.parametrize("raw", ["false", "no", "off", "0", "OFF"])
def test_show_thinking_falsy_set(tmp_path: Path, raw: str) -> None:
    """假值集合归一为**关** —— 不得因 `bool("<非空字符串>")` 为真被当作开启。"""
    assert _manager(tmp_path, _yaml_with_show_thinking(raw)).load().llm.show_thinking is False


@pytest.mark.parametrize("raw", ["maybe", "", "{}"])
def test_show_thinking_invalid_blocks_startup(tmp_path: Path, raw: str) -> None:
    """非法取值**当场拒绝并阻断启动**（不静默强转，错误信息指明键名与合法取值）。"""
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, _yaml_with_show_thinking(raw)).load()


# ---- 用户级目录回落与 .env 兜底 ----

_DOTENV_YAML = _VALID_YAML.replace("${OPENAI_API_KEY}", "${CORE_TEST_DOTENV_KEY}")


def _fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **files: str) -> Path:
    """伪造 ~/.core-agent/：写入 files（相对名 → 内容）并劫持 Path.home。"""
    core_dir = tmp_path / "home" / ".core-agent"
    core_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        _write(core_dir / name, text)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    return core_dir


def test_yaml_fallback_to_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_cwd = tmp_path / "cwd"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)
    _fake_home(tmp_path, monkeypatch, **{"config.yaml": _VALID_YAML})

    config = ConfigManager(environ={"OPENAI_API_KEY": "sk-test"}).load()

    assert config.llm.model == "gpt-4o"


def test_explicit_path_no_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_home(tmp_path, monkeypatch, **{"config.yaml": _VALID_YAML})

    manager = ConfigManager(tmp_path / "missing.yaml", environ={"OPENAI_API_KEY": "sk-test"})
    with pytest.raises(ConfigurationError):
        manager.load()


def test_env_file_backfills_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORE_TEST_DOTENV_KEY", raising=False)
    empty_cwd = tmp_path / "cwd"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)
    _fake_home(
        tmp_path,
        monkeypatch,
        **{"config.yaml": _DOTENV_YAML, ".env": "CORE_TEST_DOTENV_KEY=sk-from-dotenv\n"},
    )

    manager = ConfigManager()  # environ 未注入 → 进程 env + ~/.core-agent/.env 兜底
    config = manager.load()
    assert manager.resolve_secret("${CORE_TEST_DOTENV_KEY}") == "sk-from-dotenv"
    assert config.llm.provider == "openai"


def test_process_env_wins_over_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORE_TEST_DOTENV_KEY", "sk-from-os")
    empty_cwd = tmp_path / "cwd"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)
    _fake_home(
        tmp_path,
        monkeypatch,
        **{"config.yaml": _DOTENV_YAML, ".env": "CORE_TEST_DOTENV_KEY=sk-from-dotenv\n"},
    )

    manager = ConfigManager()

    assert manager.resolve_secret("${CORE_TEST_DOTENV_KEY}") == "sk-from-os"


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


# ---- 写回的可逆效应（change `0130` / ADR-0123，账本 E68） ----


def test_write_patch_rollback_restores_yaml_bytes(tmp_path: Path) -> None:
    """回滚 SHALL 恢复写盘前的 **原文**（含注释），而非重新 dump 出的等价内容。"""
    original = _VALID_YAML + "# 用户注释：与 dump 形态不可互逆\n"
    effects = EffectTracker()
    manager = _manager(tmp_path, original, effects=effects)
    manager.load()
    manager.write_patch({"llm": {"model": "gpt-4.1"}})
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") != original  # 写盘后已变

    report = effects.rollback("config")

    assert report.undo_failed == []
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == original


def test_write_patch_and_apply_change_share_config_trace(tmp_path: Path) -> None:
    """内存变更与写盘变更同记在 `config` trace ⇒ 一次回滚两态一并回退。"""
    effects = EffectTracker()
    manager = _manager(tmp_path, _VALID_YAML, effects=effects)
    manager.load()
    assert manager.is_enabled("voice_output") is False

    patch = {"features": {"voice_output": True}}
    manager.apply_change(patch)
    manager.write_patch(patch)
    assert manager.is_enabled("voice_output") is True
    assert {e.op for e in effects.audit("config")} == {"config_apply", "config_write_patch"}

    effects.rollback("config")

    assert manager.is_enabled("voice_output") is False  # 内存已回退
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == _VALID_YAML  # 磁盘已回退


def test_write_patch_records_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """账记在 `os.replace` **之前**：替换失败 ⇒ yaml 仍为旧值、undo 写回旧值即幂等。"""
    effects = EffectTracker()
    manager = _manager(tmp_path, _VALID_YAML, effects=effects)
    manager.load()

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError  # 模拟替换失败（磁盘错）

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        manager.write_patch({"llm": {"model": "gpt-4.1"}})

    assert [e.op for e in effects.audit("config")] == ["config_write_patch"]  # 替换前已记账
    report = effects.rollback("config")

    assert report.undo_failed == []  # undo 未失败（写回旧值幂等）
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == _VALID_YAML


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


# ---- config_value：装配前单键解析（账本 E21） ----


def test_config_value_reads_yaml_layer(tmp_path: Path) -> None:
    """CLI 前置判定要能看到 yaml 层：pet.* 从 config.yaml 读出（此前只解析 CLI/env）。"""
    manager = _manager(tmp_path, _PET_YAML)
    assert manager.config_value("pet.enabled") is True
    assert manager.config_value("pet.persons_dir") == "./pets"


def test_config_value_priority_chain(tmp_path: Path) -> None:
    """优先级链 CLI flag > env > config.yaml > 缺省，逐层压过。"""
    manager = _manager(
        tmp_path,
        _PET_YAML,
        environ={"CORE_PET_ENABLED": "false"},
        cli={"pet.enabled": True},
    )
    assert manager.config_value("pet.enabled") is True  # CLI 压过 env 与 yaml
    env_only = _manager(tmp_path, _PET_YAML, environ={"CORE_PET_ENABLED": "false"})
    # env 层取字符串原文（与 resolve 口径一致），归一化（如 _as_bool）是调用方的事
    assert env_only.config_value("pet.enabled") == "false"


def test_config_value_falls_back_to_default(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML)
    assert manager.config_value("pet.enabled") is False
    assert manager.config_value("pet.persons_dir") == "persons"


def test_config_value_tolerates_missing_file(tmp_path: Path) -> None:
    """配置文件不存在按「无 yaml 层」处理（不抛 ConfigurationError）。"""
    manager = ConfigManager(tmp_path / "nope.yaml", environ={"OPENAI_API_KEY": "sk-test"})
    assert manager.config_value("pet.enabled") is False


def test_config_value_maps_key_differing_from_map_to(tmp_path: Path) -> None:
    """yaml 键按 ``map_to`` 嵌套、解析键为 ``ConfigSpec.key``，两者不同也须对上。"""
    manager = _manager(tmp_path, _VALID_YAML + "im:\n  corp_id: wx123\n  secret: ${IM_SECRET}\n")
    assert manager.config_value("im.corp-id") == "wx123"


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


# ---- change 0056：密钥引用校验对称化 + permission.mode 枚举校验 ----


def _im_yaml(secret_line: str) -> str:
    return (
        "llm:\n  provider: openai\n  model: gpt-4o\n  endpoint: e\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        f"im:\n  gateway: feishu\n  corp_id: corp1\n{secret_line}\n"
    )


def test_im_empty_secret_rejected(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _im_yaml("  secret:"))
    with pytest.raises(ConfigurationError) as exc_info:
        manager.load()
    assert "im.secret" in str(exc_info.value)


def test_im_unresolvable_secret_rejected(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _im_yaml("  secret: ${IM_SECRET}"))
    with pytest.raises(ConfigurationError) as exc_info:
        manager.load()
    assert "im.secret" in str(exc_info.value)


def test_im_secret_resolvable_passes(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _im_yaml("  secret: ${IM_SECRET}"), environ={"IM_SECRET": "im-sk"})
    config = manager.load()
    assert config.im is not None
    assert config.im.secret_ref == "${IM_SECRET}"


def test_im_absent_skips_secret_check(tmp_path: Path) -> None:
    assert _manager(tmp_path, _VALID_YAML).load().im is None


def test_judgment_empty_key_rejected_when_provider_set(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        _VALID_YAML + "judgment:\n  provider: jev\n  model: m\n",
    )
    with pytest.raises(ConfigurationError) as exc_info:
        manager.load()
    assert "judgment.api_key" in str(exc_info.value)


def test_judgment_inert_section_skips_key_check(tmp_path: Path) -> None:
    """provider 为空的惰性段不校验 api_key（规格「未配置或 provider 为空 → 能力关闭」）。"""
    config = _manager(tmp_path, _VALID_YAML + "judgment:\n  base_url: http://jev.local\n").load()
    assert config.judgment is not None
    assert config.judgment.api_key_ref == ""


def test_illegal_permission_mode_rejected(tmp_path: Path) -> None:
    manager = _manager(tmp_path, _VALID_YAML, cli={"permission.mode": "yolo"})
    with pytest.raises(ConfigurationError) as exc_info:
        manager.load()
    message = str(exc_info.value)
    assert "permission.mode" in message
    assert "read-only" in message and "high-risk-block" in message


@pytest.mark.parametrize("mode", ["read-only", "interactive", "auto-approve", "high-risk-block"])
def test_permission_modes_accepted(tmp_path: Path, mode: str) -> None:
    manager = _manager(tmp_path, _VALID_YAML, cli={"permission.mode": mode})
    manager.load()
    assert manager.permission_mode() == mode


# ---- E18：未知配置段仅告警（change 0064） ----

_UNKNOWN_SECTION_YAML = _VALID_YAML + "llmm:\n  model: typo\n"


def _section_warnings(caught: list[warnings.WarningMessage]) -> list[str]:
    return [str(w.message) for w in caught if "未知配置段" in str(w.message)]


def test_unknown_section_warns_but_does_not_block(tmp_path: Path) -> None:
    """拼错的段名（llmm）→ 启动不被阻断，告警含段名，且该段保留在 extra（不静默丢弃）。"""
    manager = _manager(tmp_path, _UNKNOWN_SECTION_YAML)
    with pytest.warns(UserWarning, match="未知配置段: llmm"):
        config = manager.load()
    assert config.extra["llmm"] == {"model": "typo"}
    result = manager.validate_schema(config)
    assert result.ok is True  # 告警 ≠ 阻断
    assert any("llmm" in w for w in result.warnings)


def test_known_sections_produce_no_warning(tmp_path: Path) -> None:
    """已知段（五个结构化段 + permission + ConfigSpec 声明的 constraints）一律不告警。"""
    yaml = (
        _VALID_YAML
        + "im:\n  gateway: wecom\n  corp_id: corp\n  secret: ${IM_SECRET}\n"
        + "pet:\n  enabled: true\n"
        + "judgment:\n  provider: jev\n  api_key: ${JUDGMENT_API_KEY}\n"
        + "permission:\n  mode: read-only\n"
        + "constraints:\n  failure_threshold: 2\n"
    )
    manager = _manager(tmp_path, yaml, environ={"IM_SECRET": "s", "JUDGMENT_API_KEY": "j"})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager.load()
    assert _section_warnings(caught) == []


def test_unknown_key_inside_known_section_does_not_warn(tmp_path: Path) -> None:
    """口径只到顶层段名：已知段内部的未知子键不告警（不递归校验子段）。

    例外仅 `features` 段（其子键是模块名，见 E20① / change `0085`）——此处 `llm` 子键仍不告警。
    """
    yaml = (
        "llm:\n  provider: openai\n  model: gpt-4o\n"
        "  endpoint: https://api.openai.com/v1\n  api_key: ${OPENAI_API_KEY}\n"
        "  typo_key: 1\n"
    )
    manager = _manager(tmp_path, yaml)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager.load()
    assert _section_warnings(caught) == []


def test_validation_result_warnings_default_empty() -> None:
    """既有构造面不破：`ValidationResult(ok=True)` 的 warnings 缺省为空。"""
    assert ValidationResult(ok=True).warnings == []


# ---- E20①：features 段未知模块名仅告警（change 0085） ----

_KNOWN_MODULES = ("pet", "beast", "evolution")

_FEATURE_TYPO_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
features:
  peet: false
"""


def _feature_warnings(caught: list[warnings.WarningMessage]) -> list[str]:
    return [str(w.message) for w in caught if "未知功能开关" in str(w.message)]


def test_unknown_feature_module_warns_but_does_not_block(tmp_path: Path) -> None:
    """拼错的模块名（peet）→ 不阻断，告警含子键名（暴露静默 no-op）。"""
    manager = _manager(tmp_path, _FEATURE_TYPO_YAML, known_modules=_KNOWN_MODULES)
    with pytest.warns(UserWarning, match="未知功能开关: features.peet"):
        config = manager.load()
    result = manager.validate_schema(config)
    assert result.ok is True  # 告警 ≠ 阻断
    assert any("features.peet" in w for w in result.warnings)


def test_known_feature_module_produces_no_warning(tmp_path: Path) -> None:
    """已知模块名（pet）不告警。"""
    yaml = _FEATURE_TYPO_YAML.replace("peet", "pet")
    manager = _manager(tmp_path, yaml, known_modules=_KNOWN_MODULES)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager.load()
    assert _feature_warnings(caught) == []


def test_feature_module_not_checked_without_injection(tmp_path: Path) -> None:
    """未注入已知集合 ⇒ 不校验 features 子键（向后兼容：自定义键 / 测试夹具不告警）。"""
    manager = _manager(tmp_path, _FEATURE_TYPO_YAML)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager.load()
    assert _feature_warnings(caught) == []


def test_feature_warning_scope_only_features(tmp_path: Path) -> None:
    """作用域限 features 段：其它已知段的未知子键（llm.typo_key）不触发任何告警。"""
    yaml = (
        "llm:\n  provider: openai\n  model: gpt-4o\n"
        "  endpoint: https://api.openai.com/v1\n  api_key: ${OPENAI_API_KEY}\n"
        "  typo_key: 1\n"
        "features:\n  pet: false\n"
    )
    manager = _manager(tmp_path, yaml, known_modules=_KNOWN_MODULES)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager.load()
    assert _feature_warnings(caught) == []
    assert _section_warnings(caught) == []
