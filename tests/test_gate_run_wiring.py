"""门禁工具的组合根接线用例（change 0111 / phase-27 切片 S1）。

覆盖：`build_runtime` 后主工具面含 `tools.gate_run`，其门禁名枚举与单一真源
`GATE_COMMANDS` 的键集合**逐字一致**（无第二份门禁名清单）。
"""

from __future__ import annotations

from core.ci_cd import GATE_COMMANDS
from core.configuration import ConfigManager
from core.runtime import build_runtime


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    return str(cfg)


def _runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def test_gate_run_registered_on_main_tool_face(monkeypatch, tmp_path) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    tool_ids = [definition.tool_id for definition in runtime.tools.active_tools()]
    assert "tools.gate_run" in tool_ids


def test_gate_run_gate_names_track_single_source(monkeypatch, tmp_path) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    definition = next(d for d in runtime.tools.active_tools() if d.tool_id == "tools.gate_run")
    assert definition.schema["properties"]["gate"]["enum"] == list(GATE_COMMANDS)
    assert definition.coeffects == ["process:spawn", "filesystem:write"]
    assert definition.reversible is False
