"""serve 单元测试（对齐契约红线：9 端点 / SSE 流式 / 错误码映射 / 三模复用同一内核）。"""

from __future__ import annotations

import pytest
from starlette import status

from core.configuration.models import LLMConfig
from core.loop import LoopEvent
from core.ui import UIAPILayer
from core.ui.fastapi_serve import build_app

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


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
