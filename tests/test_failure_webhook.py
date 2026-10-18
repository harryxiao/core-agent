"""失败通知 webhook sink（change 0281 / ADR-0271）。

覆盖：配置三面与 URL 校验（不回显值）/ 通用 JSON POST 与脱敏 / 5s 有界 /
空配置零网络 I/O / 推送失败与文件 sink 互不影响 / 取消不通知。
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from core import entry
from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.loop import LoopEvent
from core.orchestration import OrchestrationErrorCode, notify

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)
_CANARY = "sk-abcdefghijklmnop"
_WEBHOOK = "https://hooks.example.com/services/T0KEN000"


def _manager(
    tmp_path: Path,
    extra: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
) -> ConfigManager:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    manager = ConfigManager(
        yaml_path=cfg,
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    manager.load()
    return manager


class _FakeResponse:
    status = 200

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self) -> bytes:
        return b""


def _capture(
    monkeypatch: pytest.MonkeyPatch, *, exc: Exception | None = None
) -> list[tuple[Any, float]]:
    calls: list[tuple[Any, float]] = []

    def fake_urlopen(request: Any, timeout: float = 0) -> _FakeResponse:
        calls.append((request, timeout))
        if exc is not None:
            raise exc
        return _FakeResponse()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    return calls


# ---- 配置 ----


def test_webhook_spec_three_faces_and_default() -> None:
    spec = {item.key: item for item in config_specs()}["orchestration.failure_notify_webhook"]
    assert (
        spec.cli_flag,
        spec.env_var,
        spec.default,
    ) == (
        "--orchestration.failure-notify-webhook",
        "CORE_ORCHESTRATION_FAILURE_NOTIFY_WEBHOOK",
        "",
    )


def test_webhook_default_and_three_face_priority(tmp_path: Path) -> None:
    assert _manager(tmp_path).orchestration_failure_notify_webhook() == ""
    manager = _manager(
        tmp_path,
        "orchestration:\n  failure_notify_webhook: https://yaml.example.com/h\n",
        environ={"CORE_ORCHESTRATION_FAILURE_NOTIFY_WEBHOOK": "https://env.example.com/h"},
        cli={"orchestration.failure_notify_webhook": "https://cli.example.com/h"},
    )
    assert manager.orchestration_failure_notify_webhook() == "https://cli.example.com/h"


@pytest.mark.parametrize(
    "value",
    ["file:///tmp/x", "ftp://h/x", "https://", "http://", "true"],
)
def test_invalid_webhook_blocks_startup_without_echo(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigurationError) as exc:
        _manager(tmp_path, f"orchestration:\n  failure_notify_webhook: {value}\n")
    assert "非法失败通知 webhook" in str(exc.value)
    assert value not in str(exc.value)


# ---- 发送 ----


def test_notify_failure_posts_redacted_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture(monkeypatch)
    entry._notify_failure(
        "",
        task_id="t1",
        session_id="s1",
        goal=f"处理 {_CANARY}",
        code="TASK_TIMEOUT",
        reason=f"超时 {_CANARY}",
        webhook=_WEBHOOK,
    )
    assert len(calls) == 1
    request, timeout = calls[0]
    assert timeout == 5.0  # noqa: PLR2004 — 有界推送
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    body = json.loads(request.data.decode("utf-8"))
    assert body["event"] == "task_failed"
    assert body["task_id"] == "t1"
    assert body["session_id"] == "s1"
    assert body["code"] == "TASK_TIMEOUT"
    assert _CANARY not in json.dumps(body)
    assert "<redacted>" in body["reason"]
    assert body["text"].startswith("[core-agent] 任务失败 t1")


def test_empty_webhook_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)
    entry._notify_failure("", task_id="t", session_id="", goal="g", code="X", reason="r")
    assert calls == []


def test_webhook_failure_does_not_block_file_sink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _capture(monkeypatch, exc=urllib.error.URLError(f"boom {_WEBHOOK}"))
    path = tmp_path / "notify.jsonl"
    entry._notify_failure(
        str(path),
        task_id="t",
        session_id="",
        goal="g",
        code="X",
        reason="r",
        webhook=_WEBHOOK,
    )  # 不抛
    assert path.read_text(encoding="utf-8").count("\n") == 1
    err = capsys.readouterr().err
    assert "webhook" in err
    assert "T0KEN000" not in err  # URL 可能内嵌令牌 ⇒ 绝不回显


def test_file_sink_failure_does_not_block_webhook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _capture(monkeypatch)
    entry._notify_failure(
        str(tmp_path),  # 目录不可写为文件 ⇒ 文件 sink 失败
        task_id="t",
        session_id="",
        goal="g",
        code="X",
        reason="r",
        webhook=_WEBHOOK,
    )
    assert len(calls) == 1


class _FailingOrchestrator:
    def __init__(self, code: str) -> None:
        self.code = code

    async def astream(self, *args: Any, **kwargs: Any) -> Any:
        yield LoopEvent(
            "task_failed",
            {"task_id": "t", "code": self.code, "reason": "boom"},
        )


def test_stream_task_posts_webhook_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)
    failed = asyncio.run(
        entry._stream_task(
            _FailingOrchestrator(OrchestrationErrorCode.SUBTASK_EXECUTION_FAILED),
            "t",
            "goal",
            None,
            None,
            None,
            "",
            notify_webhook=_WEBHOOK,
        )
    )
    assert failed is True
    assert len(calls) == 1


def test_stream_task_skips_webhook_on_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)
    asyncio.run(
        entry._stream_task(
            _FailingOrchestrator(OrchestrationErrorCode.TASK_CANCELLED),
            "t",
            "goal",
            None,
            None,
            None,
            "",
            notify_webhook=_WEBHOOK,
        )
    )
    assert calls == []
