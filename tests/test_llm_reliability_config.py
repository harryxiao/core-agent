"""LLM 调用超时 / 重试可配置（change 0232）。

规格 `configuration`「LLM 提供商配置（必选）」：新增**可选**子项 `timeout`（单次调用超时上限，
秒，须 > 0，缺省 60.0）与 `max_retries`（最大重试次数，须 ≥ 0 的整数，缺省 3），三面由 ConfigSpec
单一真源生成、非法取值校验期阻断；规格 `llm-provider`「模型调用可靠性」：缺省 60.0s / 3 次
**缺省不变**、可经配置覆盖并由组合根注入实现。

本文件证明：三面齐备、**未配置时缺省与实现类缺省逐字一致**（60.0 / 3 ⇒ 行为零改变）、非法取值
**校验期阻断**（不静默强转）、组合根**真的**把配置值注入主 provider（30.0 / 1）。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.llm_provider import StdlibLLMProvider
from core.runtime import build_runtime

# 缺省 = StdlibLLMProvider 类缺省（规格钉住的兼容边界，change 0232）
_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MAX_RETRIES = 3

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _write_config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path,
    extra: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
    load: bool = True,
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    if load:
        manager.load()
    return manager


# ---- ConfigSpec 单一真源面 ----


def test_specs_declare_timeout_and_max_retries() -> None:
    """两键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备（单一真源）。"""
    specs = {spec.key: spec for spec in config_specs()}
    timeout = specs["llm.timeout"]
    retries = specs["llm.max_retries"]
    assert (timeout.cli_flag, timeout.env_var, timeout.map_to) == (
        "--llm.timeout",
        "CORE_LLM_TIMEOUT",
        "llm.timeout",
    )
    assert timeout.default == _DEFAULT_TIMEOUT
    assert (retries.cli_flag, retries.env_var, retries.map_to) == (
        "--llm.max-retries",
        "CORE_LLM_MAX_RETRIES",
        "llm.max_retries",
    )
    assert retries.default == _DEFAULT_MAX_RETRIES


# ---- 缺省不变（未配置 ⇒ 与实现类缺省逐字一致） ----


def test_defaults_match_provider_class_defaults(tmp_path: Path) -> None:
    """未配置两键 ⇒ 回落 60.0 / 3（与 `StdlibLLMProvider` 类缺省逐字一致）。"""
    llm = _manager(tmp_path).load().llm
    assert llm.timeout == _DEFAULT_TIMEOUT
    assert llm.max_retries == _DEFAULT_MAX_RETRIES


# ---- 三面优先级链 ----


def test_from_yaml(tmp_path: Path) -> None:
    yaml_timeout, yaml_retries = 30.0, 1
    llm = _manager(tmp_path, "  timeout: 30\n  max_retries: 1\n").load().llm
    assert (llm.timeout, llm.max_retries) == (yaml_timeout, yaml_retries)


def test_env_overrides_yaml(tmp_path: Path) -> None:
    env_timeout, env_retries = 45.0, 2
    llm = (
        _manager(
            tmp_path,
            "  timeout: 30\n  max_retries: 1\n",
            environ={"CORE_LLM_TIMEOUT": "45", "CORE_LLM_MAX_RETRIES": "2"},
        )
        .load()
        .llm
    )
    assert (llm.timeout, llm.max_retries) == (env_timeout, env_retries)


def test_cli_overrides_env_and_yaml(tmp_path: Path) -> None:
    """优先级链 CLI flag > env > config.yaml（配置能力的既有口径）。"""
    cli_timeout = 12.5
    llm = (
        _manager(
            tmp_path,
            "  timeout: 30\n",
            environ={"CORE_LLM_TIMEOUT": "45"},
            cli={"llm.timeout": "12.5"},
        )
        .load()
        .llm
    )
    assert llm.timeout == cli_timeout


# ---- 非法取值校验期阻断（不静默强转） ----


@pytest.mark.parametrize("value", ["0", "-1", "abc", "true"])
def test_invalid_timeout_blocks_startup(tmp_path: Path, value: str) -> None:
    """超时须 > 0：0 / 负数 / 非数值 / 布尔一律阻断启动。"""
    with pytest.raises(ConfigurationError, match="非法调用超时"):
        _manager(tmp_path, f"  timeout: {value}\n")


@pytest.mark.parametrize("value", ["-1", "1.5", "abc", "true"])
def test_invalid_max_retries_blocks_startup(tmp_path: Path, value: str) -> None:
    """重试次数须为 ≥0 的整数：负数 / 小数 / 非数值 / 布尔一律阻断启动。"""
    with pytest.raises(ConfigurationError, match="非法最大重试次数"):
        _manager(tmp_path, f"  max_retries: {value}\n")


def test_invalid_value_does_not_silently_fall_back(tmp_path: Path) -> None:
    """非法取值**不得**退化成缺省（否则配置错误被掩盖成「看起来正常」）。"""
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, "  timeout: 0\n")


# ---- 段名白名单（ConfigSpec 声明段自动进白名单） ----


def test_llm_keys_do_not_trigger_unknown_section_warning(tmp_path: Path) -> None:
    """`llm.timeout` / `llm.max_retries` 已由 ConfigSpec 声明 ⇒ 不触发「未知配置段」告警。"""
    env_timeout = 30.0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager = _manager(tmp_path, environ={"CORE_LLM_TIMEOUT": "30"})
    assert [w for w in caught if "未知配置段" in str(w.message)] == []
    assert manager.load().llm.timeout == env_timeout


# ---- 组合根注入（接线） ----


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _provider(runtime: object) -> StdlibLLMProvider:
    return cast(StdlibLLMProvider, runtime.llm)  # type: ignore[attr-defined]


def test_build_runtime_injects_configured_values(tmp_path: Path, state_dir: Path) -> None:
    """组合根把配置值注入主 provider（不再是写死的类默认）。"""
    runtime = build_runtime(
        ConfigManager(
            yaml_path=_write_config(tmp_path, "  timeout: 30\n  max_retries: 1\n"),
            environ={"OPENAI_API_KEY": "sk-test"},
        )
    )
    provider = _provider(runtime)
    assert (provider._timeout, provider._max_retries) == (30.0, 1)  # noqa: SLF001 — 接线断言


def test_build_runtime_defaults_unchanged(tmp_path: Path, state_dir: Path) -> None:
    """未配置 ⇒ 组合根注入类缺省（变更前后行为逐字一致）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path), environ={"OPENAI_API_KEY": "sk-test"})
    )
    provider = _provider(runtime)
    assert provider._timeout == _DEFAULT_TIMEOUT  # noqa: SLF001
    assert provider._max_retries == _DEFAULT_MAX_RETRIES  # noqa: SLF001
