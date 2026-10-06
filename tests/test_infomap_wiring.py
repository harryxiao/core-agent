"""信息地图的组合根接线用例（change 0140 / 账本 E77）。

覆盖：`build_runtime` 后长文档（Core.md「## 项目信息」段）真的进了信息地图、装配器
`build()` 真的读地图（目录层注入）、取详情的消费面 `tools.context_read` 在主工具面可达。
"""

from __future__ import annotations

from core.configuration import ConfigManager
from core.loop import LoopContext
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
    monkeypatch.setenv("HOME", str(tmp_path))  # 隔离全局级，避免读到真实 ~/.core/Core.md
    project = tmp_path / "proj"
    project.mkdir()
    (project / "Core.md").write_text("## 项目信息\n- 本项目用 uv 管理依赖\n", encoding="utf-8")
    monkeypatch.chdir(project)  # 项目级 Core.md 按 cwd 向上查找命中
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def test_context_read_registered_on_main_tool_face(monkeypatch, tmp_path) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    tool_ids = [definition.tool_id for definition in runtime.tools.active_tools()]
    assert "tools.context_read" in tool_ids


def test_core_profile_indexed_and_pointers_reach_the_prompt(monkeypatch, tmp_path) -> None:
    """E77 主体：地图**可达** —— 目录层进装配包，且真的渲染进 system prompt。"""
    runtime = _runtime(monkeypatch, tmp_path)
    planner = runtime.loop._planner
    pack = planner._assembler.build("项目信息", "reason", budget=2048)
    assert [p["pointer"] for p in pack.pointers] == ["core-profile#项目信息"]

    prompt = planner._system_prompt(LoopContext(messages=[]))
    assert "文档目录（按需取详情，勿请求全文）：" in prompt
    assert "- core-profile#项目信息" in prompt


def test_context_read_tool_fetches_pointer_payload(monkeypatch, tmp_path) -> None:
    """消费面闭环：模型按指针取详情（不由全文顶替）。"""
    runtime = _runtime(monkeypatch, tmp_path)
    result = runtime.tools.invoke(
        "tools.context_read", {"pointer": "core-profile#项目信息"}, trace_id="t"
    )
    assert result.ok, result.error
    assert result.data == {"pointer": "core-profile#项目信息", "detail": "项目信息"}


def test_context_read_unknown_pointer_is_empty_not_error(monkeypatch, tmp_path) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    result = runtime.tools.invoke("tools.context_read", {"pointer": "absent#nope"}, trace_id="t")
    assert result.ok, result.error
    assert result.data["detail"] == ""
