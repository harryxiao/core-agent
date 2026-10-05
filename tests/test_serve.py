"""serve 单元测试（对齐契约红线：10 端点 / SSE 流式 / 错误码映射 / 三模复用同一内核）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette import status

from core.configuration import ConfigManager
from core.configuration.models import LLMConfig
from core.loop import DefaultLoop, LoopEvent
from core.ui import UIAPILayer
from core.ui.fastapi_serve import build_app

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


class FakeLoop:
    """产出受控 LoopEvent 流的 loop 替身。"""

    def __init__(self, events: list[LoopEvent]) -> None:
        self._events = events

    async def astream(self, user_input: str, *, session_id: str = ""):
        for event in self._events:
            yield event


def _llm() -> LLMConfig:
    return LLMConfig(
        provider="openai", model="gpt-4o", endpoint="https://x", api_key_ref="${OPENAI_API_KEY}"
    )


def _client() -> tuple[UIAPILayer, object]:
    api = UIAPILayer(loop=FakeLoop([LoopEvent("loop_finished", {"reply": "done"})]))
    api.set_llm_config(_llm())
    return api, TestClient(build_app(api))


def test_session_create_and_memory_roundtrip() -> None:
    _, client = _client()
    session_id = client.post("/session", json={"mode": "cli"}).json()["session_id"]
    assert session_id
    resp = client.get("/memory", params={"session_id": session_id})
    assert resp.status_code == status.HTTP_200_OK


def test_memory_unknown_session_404() -> None:
    _, client = _client()
    resp = client.get("/memory", params={"session_id": "nope"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND


def test_compact_ok() -> None:
    _, client = _client()
    session_id = client.post("/session", json={"mode": "cli"}).json()["session_id"]
    resp = client.post("/session/compact", json={"session_id": session_id})
    assert resp.status_code == status.HTTP_200_OK


def test_tools_list() -> None:
    _, client = _client()
    resp = client.get("/tools")
    assert resp.status_code == status.HTTP_200_OK
    assert "tools" in resp.json()


def test_llm_config_roundtrip() -> None:
    _, client = _client()
    assert client.get("/llm-config").json()["api_key_ref"] == "${OPENAI_API_KEY}"
    client.put(
        "/llm-config",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "endpoint": "https://x",
            "api_key_ref": "${OPENAI_API_KEY}",
        },
    )
    assert client.get("/llm-config").json()["model"] == "gpt-4o-mini"


def test_llm_config_roundtrip_window_and_budget(tmp_path: Path) -> None:
    """PUT 带窗口/预算旋钮 ⇒ GET 回显**派生后的生效值**且已落盘、loop 已热更新（change 0099）。"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_LLM_SECTION, encoding="utf-8")
    mgr = ConfigManager(yaml_path=cfg_path, environ={"OPENAI_API_KEY": "sk-test"})
    mgr.load()
    loop = DefaultLoop()
    client = TestClient(build_app(UIAPILayer(loop=loop, config=mgr)))

    resp = client.put(
        "/llm-config",
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "endpoint": "https://x",
            "api_key_ref": "${OPENAI_API_KEY}",
            "context_window": 131072,
            "output_reserve": 4096,
            "max_rounds": 3,
        },
    )
    assert resp.status_code == status.HTTP_200_OK

    body = client.get("/llm-config").json()
    assert body["context_window"] == 131072  # noqa: PLR2004 — 即 PUT 传入值
    assert body["token_budget"] == 131072 - 4096  # 派生值 = 窗口 - 预留
    assert body["max_rounds"] == 3  # noqa: PLR2004 — 即 PUT 传入值
    assert (loop._max_rounds, loop._token_budget) == (3, 131072 - 4096)  # noqa: SLF001 — 热生效
    assert "131072" in cfg_path.read_text(encoding="utf-8")  # 落盘（非仅内存态）


def test_llm_config_invalid_returns_400(tmp_path: Path) -> None:
    """窗口不敷预留 ⇒ 400 + 结构化错误码（校验期阻断，不静默兜底）。"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_LLM_SECTION, encoding="utf-8")
    mgr = ConfigManager(yaml_path=cfg_path, environ={"OPENAI_API_KEY": "sk-test"})
    mgr.load()
    client = TestClient(build_app(UIAPILayer(loop=DefaultLoop(), config=mgr)))

    resp = client.put(
        "/llm-config",
        json={
            "provider": "openai",
            "model": "gpt-4o",
            "endpoint": "https://x",
            "api_key_ref": "${OPENAI_API_KEY}",
            "context_window": 4096,
            "output_reserve": 8192,
        },
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["error"] == "UI_LLM_CONFIG_INVALID"


def test_barge_in_501() -> None:
    _, client = _client()
    resp = client.post("/barge-in")
    assert resp.status_code == status.HTTP_501_NOT_IMPLEMENTED


def test_run_sse_streams_result() -> None:
    _, client = _client()
    session_id = client.post("/session", json={"mode": "cli"}).json()["session_id"]
    with client.stream("POST", "/run", json={"session_id": session_id, "user_input": "hi"}) as resp:
        assert resp.status_code == status.HTTP_200_OK
        body = "".join(resp.iter_text())
    assert "loop.result" in body


def test_run_unknown_session_sse_error() -> None:
    _, client = _client()
    with client.stream("POST", "/run", json={"session_id": "nope", "user_input": "hi"}) as resp:
        body = "".join(resp.iter_text())
    assert "UI_SESSION_NOT_FOUND" in body


def test_sessions_endpoint_lists_created() -> None:
    """`GET /sessions`（change 0094）：枚举注册表内对话会话。"""
    _, client = _client()
    session_id = client.post("/session", json={"mode": "cli"}).json()["session_id"]

    resp = client.get("/sessions")

    assert resp.status_code == status.HTTP_200_OK
    entries = resp.json()["sessions"]
    assert [entry["session_id"] for entry in entries] == [session_id]
    assert entries[0]["mode"] == "cli"


def test_sessions_endpoint_empty() -> None:
    _, client = _client()
    resp = client.get("/sessions")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"sessions": []}
