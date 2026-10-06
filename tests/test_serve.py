"""serve 单元测试（对齐契约红线：11 端点 / SSE 流式 / 错误码映射 / 三模复用同一内核）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette import status

from core.configuration import ConfigManager
from core.configuration.models import LLMConfig
from core.loop import DefaultLoop, LoopEvent
from core.memory import TranscriptStore
from core.ui import UIAPILayer, fastapi_serve
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


# ---- 会话转录读取面（change 0115 / phase-28 E49）----


def _client_with_transcript(tmp_path: Path) -> tuple[UIAPILayer, object, TranscriptStore]:
    store = TranscriptStore(tmp_path / "messages.jsonl")
    api = UIAPILayer(
        loop=FakeLoop([LoopEvent("loop_finished", {"reply": "done"})]), transcript=store
    )
    api.set_llm_config(_llm())
    return api, TestClient(build_app(api)), store


def test_session_messages_returns_transcript(tmp_path: Path) -> None:
    _, client, store = _client_with_transcript(tmp_path)
    session_id = client.post("/session", json={"mode": "cli"}).json()["session_id"]
    store.append(session_id, "user", "第一问")
    store.append(session_id, "assistant", "第一答")

    resp = client.get(f"/session/{session_id}/messages")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["session_id"] == session_id
    assert [m["content"] for m in body["messages"]] == ["第一问", "第一答"]


def test_session_messages_unknown_session_404(tmp_path: Path) -> None:
    """未登记标识仍拒绝（fail-closed，不放宽既有会话校验）。"""
    _, client, _ = _client_with_transcript(tmp_path)

    resp = client.get("/session/nope/messages")

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["error"] == "UI_SESSION_NOT_FOUND"


def test_sessions_entry_enriched_with_derived_title(tmp_path: Path) -> None:
    _, client, store = _client_with_transcript(tmp_path)
    session_id = client.post("/session", json={"mode": "cli"}).json()["session_id"]
    store.append(session_id, "user", "看看标题")

    entry = client.get("/sessions").json()["sessions"][0]

    assert entry["session_id"] == session_id
    assert entry["mode"] == "cli"
    assert entry["title"] == "看看标题"
    assert isinstance(entry["updated_at"], (int, float))


def test_sessions_entry_without_transcript_gets_empty_title(tmp_path: Path) -> None:
    """无转录的会话 SHALL NOT 被伪造出标题：形状齐备但 `title` 为空串。

    `updated_at` 回落注册表 `created_at`（空会话的「最近活跃」即创建时刻）——
    消费方无需为缺键特判。
    """
    _, client, _ = _client_with_transcript(tmp_path)
    session_id = client.post("/session", json={"mode": "cli"}).json()["session_id"]

    entry = client.get("/sessions").json()["sessions"][0]

    assert entry["session_id"] == session_id
    assert entry["title"] == ""
    assert entry["updated_at"] == entry["created_at"]


def test_sessions_entry_shape_unchanged_without_transcript() -> None:
    """未注入转录存储 ⇒ 条目形状只增不减（既有消费方不受影响）。"""
    _, client = _client()
    client.post("/session", json={"mode": "cli"})

    entry = client.get("/sessions").json()["sessions"][0]

    assert set(entry) == {"session_id", "mode", "created_at"}


# ---- SPA 静态挂载（change 0100）----


def test_without_dist_is_api_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """缺 SPA 产物 ⇒ 纯 API 模式照常可用（后端不硬依赖前端产物，可独立验收）。"""
    monkeypatch.setattr(fastapi_serve, "_DIST_DIR", tmp_path / "nope")
    _, client = _client()
    assert client.get("/llm-config").status_code == status.HTTP_200_OK
    assert client.get("/").status_code == status.HTTP_404_NOT_FOUND


def test_with_dist_serves_spa_without_shadowing_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """有产物 ⇒ `/` 是 SPA，且**既有端点不被静态兜底吞掉**（挂载顺序契约）。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa-shell</html>", encoding="utf-8")
    monkeypatch.setattr(fastapi_serve, "_DIST_DIR", dist)

    _, client = _client()

    root = client.get("/")
    assert root.status_code == status.HTTP_200_OK
    assert "spa-shell" in root.text
    assert client.get("/llm-config").status_code == status.HTTP_200_OK
    assert client.get("/tools").status_code == status.HTTP_200_OK
