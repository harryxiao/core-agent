"""L2 软上限的组合根接线（change 0251 / ADR-0241 / 台账 E187）。

证明 `memory.l2_soft_max_entries` 经 ConfigSpec 单一真源三面齐备、缺省未启用、非法取值
归一为未启用，且组合根真的把配置值注入 `MemoryStore`（此前能力存在但生产不可达）。
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import MemoryEntry, MemoryStore
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


def _entry(entry_id: str, *, age: float = 0.0) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=f"{entry_id} 内容",
        tags=[],
        source="loop",
        trace_id="t",
        ts=time.time() - age,
        kind="episodic",
    )


def _memory(runtime: object) -> MemoryStore:
    return cast(MemoryStore, runtime.memory)  # type: ignore[attr-defined]


# ---- 配置三面 ----


def test_spec_declares_l2_soft_cap() -> None:
    spec = {spec.key: spec for spec in config_specs()}["memory.l2_soft_max_entries"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-l2-soft-max-entries",
        "CORE_MEMORY_L2_SOFT_MAX_ENTRIES",
        None,
        "memory.l2_soft_max_entries",
    )


def test_default_is_disabled(tmp_path: Path) -> None:
    """未配置 ⇒ None（不触发上限检查，与变更前逐字一致）。"""
    assert _manager(tmp_path).l2_soft_max_entries() is None


def test_yaml_enables_cap(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "memory:\n  l2_soft_max_entries: 64\n")

    assert manager.l2_soft_max_entries() == 64  # noqa: PLR2004


def test_env_overrides_yaml(tmp_path: Path) -> None:
    """env 面可达（字符串口径经 `_parse_int` 归一）。"""
    manager = _manager(
        tmp_path,
        "memory:\n  l2_soft_max_entries: 64\n",
        environ={"CORE_MEMORY_L2_SOFT_MAX_ENTRIES": "7"},
    )

    assert manager.l2_soft_max_entries() == 7  # noqa: PLR2004


@pytest.mark.parametrize("raw", ["0", "-3", "true", "1.5", "abc"])
def test_invalid_values_normalize_to_disabled(tmp_path: Path, raw: str) -> None:
    """非法取值 ⇒ None（禁用，不阻断启动；`0` 若直通会清空 L2）。"""
    manager = _manager(tmp_path, f"memory:\n  l2_soft_max_entries: {raw}\n")

    assert manager.l2_soft_max_entries() is None


def test_memory_section_is_not_reported_unknown(tmp_path: Path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _manager(tmp_path, "memory:\n  l2_soft_max_entries: 64\n")

    assert [w for w in caught if "未知配置段" in str(w.message)] == []


# ---- 组合根接线 ----


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def test_build_runtime_default_wires_no_cap(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _memory(runtime)._l2_soft_max_entries is None  # noqa: SLF001 — 接线断言


def test_build_runtime_wires_configured_cap(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  l2_soft_max_entries: 2\n"))
    )

    assert _memory(runtime)._l2_soft_max_entries == 2  # noqa: SLF001,PLR2004


def test_configured_cap_collects_l2_on_write(tmp_path: Path, state_dir: Path) -> None:
    """端到端：配置后写入即收口（不等待维护节拍）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  l2_soft_max_entries: 2\n"))
    )
    store = _memory(runtime)
    for i in range(3):
        store.write("L2", _entry(f"m{i}", age=30 * 86400.0))

    layers = dict(store.index().entries)
    active = [entry_id for entry_id, layer in layers.items() if layer == "L2"]
    assert len(active) <= 2  # noqa: PLR2004
    assert any(layer == "L4" for layer in layers.values())
