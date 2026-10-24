"""后台派生调用的推理档位透传（change 0320 / ADR-0310）。

组合根 `_llm_text` 接缝（会话摘要 / 关键事实抽取 / SOP / 沉淀 / 进化）此前只构造
`LLMRequest(messages, model)`，**丢掉**了用户配置的 `llm.reasoning_effort` —— 前台 6 处
planner 调用全部下发该字段。后果：后台摘要按端点默认档位长时间思考，实测单次 44.8s /
4988 completion tokens，撞上全局 60s 超时 ⇒ 压实反复超时、摘要永不落库。

本文件钉两态：配置时**每个**后台请求携带同值；未配置时**不下发**（逐字不变）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.configuration import ConfigManager
from core.llm_provider import LLMRequest, LLMResponse, StdlibLLMProvider, TokenUsage
from core.memory import MemoryEntry
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)

# 同一段假输出同时满足两条消费者：摘要器只要求非空；关键事实抽取要求可解析 JSON 数组。
_FAKE_OUTPUT = '[{"entity": "测试实体", "value": "测试取值"}]'
_SESSION = "s-0320"


class _Recorder:
    """捕获后台 provider 收到的请求（不打桩网络，只打桩 `acompletion`）。"""

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def patch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def _fake(_self: StdlibLLMProvider, request: LLMRequest) -> LLMResponse:
            self.requests.append(request)
            return LLMResponse(
                content=_FAKE_OUTPUT,
                usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
                finish_reason="stop",
                provider="test",
                model="test-model",
            )

        monkeypatch.setattr(StdlibLLMProvider, "acompletion", _fake)


def _manager(tmp_path: Path, extra: str = "") -> ConfigManager:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    manager = ConfigManager(yaml_path=str(cfg), environ={"OPENAI_API_KEY": "sk-test"})
    manager.load()
    return manager


def _compact_once(tmp_path: Path, extra: str, recorder: _Recorder) -> list[LLMRequest]:
    """触发一次按会话收窄的压实，返回后台 provider 收到的请求（摘要 + 关键事实）。"""
    runtime = build_runtime(_manager(tmp_path, extra))
    runtime.memory.write(
        "L2",
        MemoryEntry(
            id="e1",
            layer="L2",
            content="事件：压缩测试",
            tags=["loop"],
            source="loop",
            trace_id="t1",
            session_id=_SESSION,
            kind="episodic",
        ),
    )
    runtime.memory.compact(session_id=_SESSION)
    return recorder.requests


@pytest.fixture(autouse=True)
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    rec.patch(monkeypatch)
    return rec


def test_background_calls_carry_configured_reasoning_effort(
    tmp_path: Path, recorder: _Recorder
) -> None:
    requests = _compact_once(tmp_path, "  reasoning_effort: low\n", recorder)

    assert requests, "压实应至少发起一次后台派生调用"
    assert {request.reasoning_effort for request in requests} == {"low"}


def test_background_calls_omit_reasoning_effort_when_unset(
    tmp_path: Path, recorder: _Recorder
) -> None:
    requests = _compact_once(tmp_path, "", recorder)

    assert requests, "压实应至少发起一次后台派生调用"
    assert {request.reasoning_effort for request in requests} == {None}
