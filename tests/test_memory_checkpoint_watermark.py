"""上下文检查点水位与配置（change 0310 / ADR-0300）。

钉住：`checkpoint_watermark` 只读零效应、取本会话最大 `seq_to`、**跨层跨状态单调**
（检查点被墓碑化 / 迁 L4 / 遗忘后仍计入，否则重复回写同一淘汰区间）；配置三面齐备、
缺省开启、非法值归一开启；组合根注入、直接构造缺省关。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.loop import DefaultLoop
from core.memory import MemoryEntry, MemoryStore
from core.plugin_registry import EffectTracker
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _checkpoint(
    seq_to: int, *, session_id: str = "s1", tags: list[str] | None = None
) -> MemoryEntry:
    entry_id = f"context_checkpoint.{session_id or 'default'}.{seq_to}"
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=f"会话检查点 seq 0-{seq_to}（1 行）",
        tags=tags if tags is not None else ["context_checkpoint", "seq_from:0", f"seq_to:{seq_to}"],
        source="context",
        trace_id=entry_id,
        session_id=session_id,
        kind="episodic",
    )


def _store() -> MemoryStore:
    return MemoryStore()


# ---- 水位读取 ----


def test_watermark_is_minus_one_without_checkpoints() -> None:
    assert _store().checkpoint_watermark("s1") == -1


def test_watermark_takes_max_seq_to() -> None:
    store = _store()
    store.write("L2", _checkpoint(3))
    store.write("L2", _checkpoint(7))

    assert store.checkpoint_watermark("s1") == 7  # noqa: PLR2004 — 水位断言


def test_watermark_is_monotonic_across_retraction_and_layer() -> None:
    """`seq_to:7` 墓碑化并迁 L4 后水位不回退。"""
    store = _store()
    store.write("L2", _checkpoint(7))
    assert store.retract("context_checkpoint.s1.7") is True
    store.migrate("context_checkpoint.s1.7", "L2", "L4")

    assert store.checkpoint_watermark("s1") == 7  # noqa: PLR2004 — 水位断言


def test_watermark_is_per_session() -> None:
    store = _store()
    store.write("L2", _checkpoint(9, session_id="a"))

    assert store.checkpoint_watermark("a") == 9  # noqa: PLR2004 — 会话隔离断言
    assert store.checkpoint_watermark("b") == -1


def test_watermark_skips_bad_seq_tags() -> None:
    store = _store()
    store.write("L2", _checkpoint(5))
    store.write("L2", _checkpoint(6, tags=["context_checkpoint", "seq_to:abc"]))

    assert store.checkpoint_watermark("s1") == 5  # noqa: PLR2004 — 水位断言


def test_watermark_ignores_non_checkpoint_entries() -> None:
    store = _store()
    store.write(
        "L2",
        MemoryEntry(
            id="plain",
            layer="L2",
            content="普通",
            tags=["seq_to:99"],
            source="loop",
            trace_id="t1",
            session_id="s1",
        ),
    )

    assert store.checkpoint_watermark("s1") == -1


def test_watermark_empty_session_is_minus_one() -> None:
    store = _store()
    store.write("L2", _checkpoint(3))

    assert store.checkpoint_watermark("") == -1


def test_watermark_has_no_effect_trace() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)
    store.write("L2", _checkpoint(3))
    before = len(tracker._effects)  # noqa: SLF001 — 零效应断言

    assert store.checkpoint_watermark("s1") == 3  # noqa: PLR2004 — 水位断言
    assert len(tracker._effects) == before  # noqa: SLF001 — 零效应断言


# ---- 配置三面 ----


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
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    manager.load()
    return manager


def test_spec_declares_context_checkpoint() -> None:
    spec = {spec.key: spec for spec in config_specs()}["memory.context_checkpoint"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-context-checkpoint",
        "CORE_MEMORY_CONTEXT_CHECKPOINT",
        True,
        "memory.context_checkpoint",
    )


def test_context_checkpoint_default_is_enabled(tmp_path: Path) -> None:
    assert _manager(tmp_path).context_checkpoint_enabled() is True


def test_yaml_can_disable_context_checkpoint(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "memory:\n  context_checkpoint: false\n")

    assert manager.context_checkpoint_enabled() is False


def test_env_overrides_yaml_for_context_checkpoint(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "memory:\n  context_checkpoint: true\n",
        environ={"CORE_MEMORY_CONTEXT_CHECKPOINT": "false"},
    )

    assert manager.context_checkpoint_enabled() is False


def test_cli_overrides_env_for_context_checkpoint(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        environ={"CORE_MEMORY_CONTEXT_CHECKPOINT": "false"},
        cli={"memory.context_checkpoint": True},
    )

    assert manager.context_checkpoint_enabled() is True


@pytest.mark.parametrize("raw", ["disable", "ong", '""', "2", "1.5"])
def test_invalid_context_checkpoint_normalizes_to_enabled(tmp_path: Path, raw: str) -> None:
    manager = _manager(tmp_path, f"memory:\n  context_checkpoint: {raw}\n")

    assert manager.context_checkpoint_enabled() is True


def test_direct_loop_construction_defaults_off() -> None:
    loop = DefaultLoop(planner=lambda ctx: None)

    assert loop._context_checkpoint is False  # noqa: SLF001 — 缺省逐字不变


# ---- 组合根接线 ----


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _loop(runtime: object) -> DefaultLoop:
    return cast(DefaultLoop, runtime.loop)  # type: ignore[attr-defined]


def test_build_runtime_wires_context_checkpoint(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _loop(runtime)._context_checkpoint is True  # noqa: SLF001 — 接线断言


def test_build_runtime_wires_context_checkpoint_off(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  context_checkpoint: false\n"))
    )

    assert _loop(runtime)._context_checkpoint is False  # noqa: SLF001 — 接线断言
