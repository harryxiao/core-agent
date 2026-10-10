"""重要度闸门开关与组合根接线（change 0181 / ADR-0172 / 台账 E118）。

证明新键 `memory.importance_gate` 经 ConfigSpec **单一真源**三面齐备、`memory:` 段不报
「未知配置段」（声明段自动进白名单）、缺省 **false** ⇒ 组合根**不注入**评分器（写入逐字不变），
置 true ⇒ 组合根以同一 `_llm_text` 接缝构造 `score_with` 并注入 `MemoryStore`。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import MemoryStore
from core.runtime import build_runtime

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
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
    )
    manager.load()
    return manager


def test_spec_declares_importance_gate() -> None:
    """单一真源：新键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备。"""
    spec = {spec.key: spec for spec in config_specs()}["memory.importance_gate"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-importance-gate",
        "CORE_MEMORY_IMPORTANCE_GATE",
        False,
        "memory.importance_gate",
    )


def test_default_is_off(tmp_path: Path) -> None:
    """缺省 false ⇒ 闸门不评分（与变更前逐字一致）。"""
    assert _manager(tmp_path).importance_gate() is False


def test_yaml_enables_gate(tmp_path: Path) -> None:
    assert _manager(tmp_path, "memory:\n  importance_gate: true\n").importance_gate() is True


def test_env_overrides_yaml(tmp_path: Path) -> None:
    """env 面可达（字符串口径与 feature flag 同集）。"""
    manager = _manager(tmp_path, "", environ={"CORE_MEMORY_IMPORTANCE_GATE": "true"})

    assert manager.importance_gate() is True


def test_memory_section_is_not_reported_unknown(tmp_path: Path) -> None:
    """`memory:` 已由 ConfigSpec 声明 ⇒ 不触发「未知配置段」告警。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _manager(tmp_path, "memory:\n  importance_gate: true\n")

    assert [w for w in caught if "未知配置段" in str(w.message)] == []


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _memory(runtime: object) -> MemoryStore:
    return cast(MemoryStore, runtime.memory)  # type: ignore[attr-defined]


def test_build_runtime_default_wires_no_scorer(tmp_path: Path, state_dir: Path) -> None:
    """缺省 ⇒ 组合根不注入评分器（闸门走 UNWIRED 路径，写入逐字不变）。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _memory(runtime)._importance_scorer is None  # noqa: SLF001 — 接线断言


def test_build_runtime_wires_scorer_when_enabled(tmp_path: Path, state_dir: Path) -> None:
    """置 true ⇒ 组合根经 `score_with` 注入评分器（同一 `_llm_text` 接缝）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  importance_gate: true\n"))
    )

    assert _memory(runtime)._importance_scorer is not None  # noqa: SLF001 — 接线断言
