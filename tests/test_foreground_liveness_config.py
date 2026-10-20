"""0296 · 前台存活相关的三个配置键。

规格 `configuration`：`llm.background_timeout`（后台派生调用超时，秒，> 0，缺省 60.0）、
`llm.background_max_retries`（后台派生调用重试，≥ 0 整数，缺省 0）、`loop.compact_timeout`
（轮内压实总时长上限，秒，> 0，缺省 60.0）。三键经 ConfigSpec 单一真源三面齐备、非法取值
校验期阻断；组合根把后台键注入**独立** provider（主 provider 的超时/重试不变），并把
`compact_timeout` 注入生产 loop。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, cast

import pytest

import core.runtime as runtime_module
from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.loop import DefaultLoop
from core.memory import MemoryEntry
from core.runtime import build_runtime

_DEFAULT_BACKGROUND_TIMEOUT = 60.0
_DEFAULT_BACKGROUND_RETRIES = 0
_DEFAULT_COMPACT_TIMEOUT = 60.0

# 配置面样例值（独立常量：断言不与魔法数字耦合）
_YAML_COMPACT_TIMEOUT = 20.0
_ENV_COMPACT_TIMEOUT = 8.0
_CLI_BACKGROUND_TIMEOUT = 12.5
_CLI_COMPACT_TIMEOUT = 5.0
_RUNTIME_COMPACT_TIMEOUT = 7.5
_ALL_LOOPS_COMPACT_TIMEOUT = 15.0
_EXPECTED_PROVIDER_COUNT = 2

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


def test_specs_declare_liveness_keys() -> None:
    """三键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备（单一真源）。"""
    specs = {spec.key: spec for spec in config_specs()}
    background_timeout = specs["llm.background_timeout"]
    background_retries = specs["llm.background_max_retries"]
    compact_timeout = specs["loop.compact_timeout"]
    assert (background_timeout.cli_flag, background_timeout.env_var) == (
        "--llm.background-timeout",
        "CORE_LLM_BACKGROUND_TIMEOUT",
    )
    assert background_timeout.map_to == "llm.background_timeout"
    assert background_timeout.default == _DEFAULT_BACKGROUND_TIMEOUT
    assert (background_retries.cli_flag, background_retries.env_var) == (
        "--llm.background-max-retries",
        "CORE_LLM_BACKGROUND_MAX_RETRIES",
    )
    assert background_retries.default == _DEFAULT_BACKGROUND_RETRIES
    assert (compact_timeout.cli_flag, compact_timeout.env_var) == (
        "--loop.compact-timeout",
        "CORE_LOOP_COMPACT_TIMEOUT",
    )
    assert compact_timeout.map_to == "loop.compact_timeout"
    assert compact_timeout.default == _DEFAULT_COMPACT_TIMEOUT


# ---- 缺省 ----


def test_defaults_unchanged(tmp_path: Path) -> None:
    """未配置三键 ⇒ 回落 60.0 / 0 / 60.0（与规格缺省逐字一致）。"""
    manager = _manager(tmp_path)
    llm = manager.load().llm
    assert llm.background_timeout == _DEFAULT_BACKGROUND_TIMEOUT
    assert llm.background_max_retries == _DEFAULT_BACKGROUND_RETRIES
    assert manager.compact_timeout() == _DEFAULT_COMPACT_TIMEOUT


# ---- 三面优先级链 ----


def test_from_yaml(tmp_path: Path) -> None:
    llm = (
        _manager(
            tmp_path,
            "  background_timeout: 30\n  background_max_retries: 2\nloop:\n  compact_timeout: 20\n",
        )
        .load()
        .llm
    )
    assert (llm.background_timeout, llm.background_max_retries) == (30.0, 2)


def test_yaml_compact_timeout(tmp_path: Path) -> None:
    assert (
        _manager(tmp_path, "loop:\n  compact_timeout: 20\n").compact_timeout()
        == _YAML_COMPACT_TIMEOUT
    )


def test_env_overrides_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "  background_timeout: 30\n  background_max_retries: 2\nloop:\n  compact_timeout: 20\n",
        environ={
            "CORE_LLM_BACKGROUND_TIMEOUT": "15",
            "CORE_LLM_BACKGROUND_MAX_RETRIES": "1",
            "CORE_LOOP_COMPACT_TIMEOUT": "8",
        },
    )
    loaded = manager.load()
    assert (loaded.llm.background_timeout, loaded.llm.background_max_retries) == (15.0, 1)
    assert manager.compact_timeout() == _ENV_COMPACT_TIMEOUT


def test_cli_overrides_env_and_yaml(tmp_path: Path) -> None:
    """优先级链 CLI flag > env > config.yaml（配置能力的既有口径）。"""
    manager = _manager(
        tmp_path,
        "  background_timeout: 30\nloop:\n  compact_timeout: 20\n",
        environ={
            "CORE_LLM_BACKGROUND_TIMEOUT": "15",
            "CORE_LOOP_COMPACT_TIMEOUT": "8",
        },
        cli={"llm.background_timeout": "12.5", "loop.compact_timeout": "5"},
    )
    assert manager.load().llm.background_timeout == _CLI_BACKGROUND_TIMEOUT
    assert manager.compact_timeout() == _CLI_COMPACT_TIMEOUT


# ---- 非法取值校验期阻断（不静默强转） ----


@pytest.mark.parametrize("value", ["0", "-1", "abc", "true"])
def test_invalid_background_timeout_blocks_startup(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError, match="非法后台调用超时"):
        _manager(tmp_path, f"  background_timeout: {value}\n")


@pytest.mark.parametrize("value", ["-1", "1.5", "abc", "true"])
def test_invalid_background_max_retries_blocks_startup(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError, match="非法后台最大重试次数"):
        _manager(tmp_path, f"  background_max_retries: {value}\n")


@pytest.mark.parametrize("value", ["0", "-1", "abc", "true"])
def test_invalid_compact_timeout_blocks_startup(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError, match="非法压实耗时上限"):
        _manager(tmp_path, f"loop:\n  compact_timeout: {value}\n")


def test_invalid_value_does_not_silently_fall_back(tmp_path: Path) -> None:
    """非法取值**不得**退化成缺省（否则配置错误被掩盖成「看起来正常」）。"""
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, "  background_timeout: 0\n")


# ---- 段名白名单（ConfigSpec 声明段自动进白名单） ----


def test_liveness_keys_do_not_trigger_unknown_section_warning(tmp_path: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager = _manager(tmp_path, "loop:\n  compact_timeout: 20\n")
    assert [w for w in caught if "未知配置段" in str(w.message)] == []
    assert manager.compact_timeout() == _YAML_COMPACT_TIMEOUT


# ---- 组合根注入（接线） ----


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _main_loop(runtime: object) -> DefaultLoop:
    return cast(DefaultLoop, runtime.loop)  # type: ignore[attr-defined]


def test_build_runtime_injects_compact_timeout(tmp_path: Path, state_dir: Path) -> None:
    """组合根把 `loop.compact_timeout` 注入生产 loop（不再是类缺省）。"""
    runtime = build_runtime(
        ConfigManager(
            yaml_path=_write_config(tmp_path, "loop:\n  compact_timeout: 7.5\n"),
            environ={"OPENAI_API_KEY": "sk-test"},
        )
    )
    assert _main_loop(runtime)._compact_timeout == _RUNTIME_COMPACT_TIMEOUT  # noqa: SLF001 — 接线断言


def test_build_runtime_injects_compact_timeout_into_all_loops(
    tmp_path: Path, state_dir: Path
) -> None:
    """`loop.compact_timeout` 注入**全部**四个 `DefaultLoop`（主 / 子 Agent / 神兽 / 宠物）。"""
    runtime = build_runtime(
        ConfigManager(
            yaml_path=_write_config(tmp_path, "loop:\n  compact_timeout: 15\n"),
            environ={"OPENAI_API_KEY": "sk-test"},
        )
    )

    router = runtime.orchestrator._router  # noqa: SLF001 — 接线断言
    beast = runtime.beast_manager._registry.resolve("qinglong")  # noqa: SLF001
    assert beast is not None, "名册应含青龙"
    loops = {
        "main": runtime.loop,
        "subagent": router._agents["coding"].loop,  # noqa: SLF001
        "beast": runtime.beast_manager._loop_factory(beast),  # noqa: SLF001
        "pet": runtime.pet_activator._loop,  # noqa: SLF001
    }
    for name, loop in loops.items():
        assert isinstance(loop, DefaultLoop), f"{name} 应为 DefaultLoop"
        assert loop._compact_timeout == _ALL_LOOPS_COMPACT_TIMEOUT, f"{name} 未收到配置值"  # noqa: SLF001


def test_build_runtime_compact_timeout_default(tmp_path: Path, state_dir: Path) -> None:
    """未配置 ⇒ 注入规格缺省 60.0（与 loop 模块缺省同值）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path), environ={"OPENAI_API_KEY": "sk-test"})
    )
    assert _main_loop(runtime)._compact_timeout == _DEFAULT_COMPACT_TIMEOUT  # noqa: SLF001


class _Reply:
    """模型回复替身（`_llm_text` 只读取 ``.content``）。"""

    content = "摘要"


def test_background_seam_uses_background_provider(
    tmp_path: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_llm_text` 接缝（摘要/抽取/SOP/沉淀共用）走后台 provider，主 provider 零调用。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path), environ={"OPENAI_API_KEY": "sk-test"})
    )
    calls: list[str] = []

    def main_completion(_request: Any) -> _Reply:
        calls.append("main")
        return _Reply()

    def background_completion(_request: Any) -> _Reply:
        calls.append("background")
        return _Reply()

    monkeypatch.setattr(runtime.llm, "completion", main_completion)
    monkeypatch.setattr(runtime.background_llm, "completion", background_completion)

    summarizer = runtime.memory._summarizer  # noqa: SLF001 — 接线断言
    assert summarizer is not None
    summarizer(
        [MemoryEntry(id="e1", layer="L2", content="样例", tags=[], source="loop", trace_id="t1")]
    )

    assert calls == ["background"], "后台派生接缝不得落到主 provider"


def test_build_runtime_uses_separate_background_provider(
    tmp_path: Path, state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """后台派生调用走独立 provider：主 provider 超时/重试不变，后台键独立生效。"""
    created: list[dict[str, Any]] = []
    real = runtime_module.StdlibLLMProvider

    def factory(**kwargs: Any) -> Any:
        created.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(runtime_module, "StdlibLLMProvider", factory)
    build_runtime(
        ConfigManager(
            yaml_path=_write_config(
                tmp_path,
                "  timeout: 30\n"
                "  max_retries: 3\n"
                "  background_timeout: 15\n"
                "  background_max_retries: 0\n",
            ),
            environ={"OPENAI_API_KEY": "sk-test"},
        )
    )

    providers = [item for item in created if "max_retries" in item]
    assert len(providers) == _EXPECTED_PROVIDER_COUNT, "应构造主 provider 与后台 provider 各一个"
    main, background = providers
    assert (main["timeout"], main["max_retries"]) == (30.0, 3)
    assert (background["timeout"], background["max_retries"]) == (15.0, 0)
