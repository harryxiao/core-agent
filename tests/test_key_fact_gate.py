"""关键事实抽取门控与组合根接线（change 0216 / ADR-0206 / 台账 E153）。

证明新键 `memory.key_fact_extract` 经 ConfigSpec **单一真源**三面齐备、`memory:` 段不报
「未知配置段」、**缺省 `True`**（既在用能力的 kill-switch ⇒ 保留既有行为）⇒ 组合根照常经
`extract_with` 注入抽取器；显式置 false ⇒ 组合根**不注入**（`None`，压实逐字不变）；
非法取值**回落 True**（拼写错误不得静默停用在用能力）。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import KeyFact, MemoryEntry, MemoryStore
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


def test_spec_declares_key_fact_extract() -> None:
    """单一真源：新键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备，缺省 True。"""
    spec = {spec.key: spec for spec in config_specs()}["memory.key_fact_extract"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-key-fact-extract",
        "CORE_MEMORY_KEY_FACT_EXTRACT",
        True,
        "memory.key_fact_extract",
    )


def test_default_is_on(tmp_path: Path) -> None:
    """缺省 True ⇒ 抽取器照常接线（保留既有行为，非静默停用）。"""
    assert _manager(tmp_path).key_fact_extract() is True


def test_yaml_disables_gate(tmp_path: Path) -> None:
    """置 false ⇒ 关闭抽取；且 `memory:` 已声明 ⇒ 不触发「未知配置段」告警。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager = _manager(tmp_path, "memory:\n  key_fact_extract: false\n")

    assert manager.key_fact_extract() is False
    assert [w for w in caught if "未知配置段" in str(w.message)] == []


def test_env_disables_gate(tmp_path: Path) -> None:
    """env 面可达（字符串口径与 feature flag 同集）。"""
    manager = _manager(tmp_path, "", environ={"CORE_MEMORY_KEY_FACT_EXTRACT": "false"})

    assert manager.key_fact_extract() is False


def test_unknown_value_falls_back_on(tmp_path: Path) -> None:
    """非法 / 拼错取值 ⇒ 回落 **True**（一个拼写错误不得静默关掉在用能力）。"""
    assert _manager(tmp_path, "memory:\n  key_fact_extract: maybe\n").key_fact_extract() is True


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _memory(runtime: object) -> MemoryStore:
    return cast(MemoryStore, runtime.memory)  # type: ignore[attr-defined]


def test_build_runtime_default_wires_extractor(tmp_path: Path, state_dir: Path) -> None:
    """缺省 ⇒ 组合根照常注入抽取器（与引入本键前逐字等价）。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _memory(runtime)._key_fact_extractor is not None  # noqa: SLF001 — 接线断言


def test_build_runtime_omits_extractor_when_disabled(tmp_path: Path, state_dir: Path) -> None:
    """置 false ⇒ 组合根不注入抽取器（`None` ⇒ 压实逐字不变）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  key_fact_extract: false\n"))
    )

    assert _memory(runtime)._key_fact_extractor is None  # noqa: SLF001 — 接线断言


def _episodic(entry_id: str, session_id: str, content: str = "事件") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["loop"],
        source="loop",
        session_id=session_id,
        kind="episodic",
        trace_id="t",
    )


def _compact_entries(extractor: object) -> dict[str, str]:
    store = MemoryStore(summarizer=lambda entries: "摘要：事实", key_fact_extractor=extractor)  # type: ignore[arg-type]
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    return {entry.id: entry.content for entry in store.audit()}


def test_disabled_gate_only_switches_extraction() -> None:
    """逐字锚：门**只**切抽取 —— 关（None）与开（注入）的摘要产物**逐字相同**。"""
    unwired = _compact_entries(None)
    wired = _compact_entries(lambda _entries: [KeyFact(entity="部署目标", value="生产环境")])

    assert unwired["compaction.summary.s1"] == wired["compaction.summary.s1"], "摘要产物逐字不变"
    assert [eid for eid in unwired if eid.startswith("keyfact.")] == [], "关 ⇒ 无 keyfact 条目"
    assert [eid for eid in wired if eid.startswith("keyfact.")] != [], "开 ⇒ 有 keyfact 条目"
