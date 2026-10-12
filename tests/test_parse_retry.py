"""0227 · 解析失败回喂重试（承 ADR-0217）。

事故（2026-10-11 trace `1c7cfb24…`）：子 Agent 长上下文压力下产出**退化重复**形态 ——
`{` 开头、缺收尾 `}`、后随省略号垃圾与重复对象、5029 字符截断 ⇒ `_parse` 首字符分支
整体 `json.loads` 失败 ⇒ 通用文案终止回复、**无重试** ⇒ 5.6 分钟工作全部丢弃。

本文件覆盖三层：
  * **回喂重试**：`LLMPlanner(parse_retry=True)` —— 失败门（`LLM_PLAN_PARSE_FAILED` 前缀）＋
    外发门（未外发内容增量）⇒ 追加用户角色 nudge 重试**恰一次**；nudge 不携带原始退化产出；
  * **流式边界**：已逐段外发的自然语言流**不重试**；缓冲路径（`{` 开头）重试且对外只有
    第二次的动作；
  * **门控与接线**：键 `loop.parse_retry` 三面齐备、缺省**关**、非法取值阻断启动、组合根注入。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.llm_provider import LLMChunk, LLMError, LLMResponse, TokenUsage
from core.loop import Action, LLMPlanner, LoopContext
from core.runtime import build_runtime

_PARSE_FAILED = "LLM_PLAN_PARSE_FAILED"
# 事故形态的最小复刻：`{` 开头、缺最外层收尾 `}`（json.loads 失败 ⇒ 命中未闭合判据）
_DEGENERATE = '{"tool_id": "tools.file_write", "args": {"path": "a.md", "content": "x'
_GOOD_ACTION = '{"tool_id": "tools.echo", "args": {"text": "hi"}}'
_GOOD_REPLY = "任务已完成。"
_UNCLOSED_NUDGE_CAUSE = "未闭合"


def _usage() -> TokenUsage:
    return TokenUsage(prompt_tokens=0, completion_tokens=0)


class _ScriptedLLM:
    """按序出内容的假 LLM：记录每次请求（供 nudge 断言），末项重复。"""

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.requests: list[Any] = []

    def completion(self, request: Any) -> LLMResponse:
        self.requests.append(request)
        content = self._contents[min(len(self.requests) - 1, len(self._contents) - 1)]
        return LLMResponse(
            content=content,
            usage=_usage(),
            finish_reason="stop",
            provider="fake",
            model="test-model",
        )

    async def acompletion(self, request: Any) -> LLMResponse:
        return self.completion(request)


class _StreamScriptedLLM(_ScriptedLLM):
    """流式形态：把每条脚本内容切成小块流式产出（记录请求，供调用计数）。"""

    def astream(self, request: Any) -> Any:
        self.requests.append(request)
        content = self._contents[min(len(self.requests) - 1, len(self._contents) - 1)]
        return self._stream(content)

    async def _stream(self, content: str) -> Any:
        for i in range(0, len(content), 20):
            yield LLMChunk(content=content[i : i + 20])


def _ctx() -> LoopContext:
    return LoopContext(messages=[{"role": "user", "content": "写文件"}])


def _planner(llm: Any, *, parse_retry: bool = False) -> LLMPlanner:
    return LLMPlanner(cast("Any", llm), parse_retry=parse_retry)


# ── 1. 非流式路径：失败门 + 恰一次 ───────────────────────────────────────────


def test_retry_once_then_succeeds() -> None:
    """首次退化 ⇒ nudge 重试恰一次；第二次可解析 ⇒ 正常动作（本轮不因首次失败而失败）。"""
    llm = _ScriptedLLM([_DEGENERATE, _GOOD_ACTION])
    action = asyncio.run(_planner(llm, parse_retry=True)(_ctx()))

    assert action.tool_id == "tools.echo"  # 第二次产出被采用
    assert action.failed is False
    assert len(llm.requests) == 2  # noqa: PLR2004 — 恰两次模型调用，无第三次


def test_nudge_is_user_role_with_cause_not_raw() -> None:
    """nudge：**用户角色**、含成因与协议重申、**不含**原始退化产出（守 0170 边界）。"""
    marker = "UNIQUE_DEGENERATE_MARKER"
    degenerate = '{"tool_id": "tools.echo", "args": {"text": "' + marker
    llm = _ScriptedLLM([degenerate, _GOOD_ACTION])
    asyncio.run(_planner(llm, parse_retry=True)(_ctx()))

    first, second = llm.requests
    assert len(second.messages) == len(first.messages) + 1  # 追加恰一条
    nudge = second.messages[-1]
    assert nudge.role == "user"
    assert marker not in nudge.content  # 原始退化产出不回模型
    assert _UNCLOSED_NUDGE_CAUSE in nudge.content  # 成因随措辞细化进入 nudge
    assert "JSON" in nudge.content  # 输出格式协议重申


def test_retry_still_fails_exactly_two_calls() -> None:
    """两次均退化 ⇒ 失败态终止动作（第二次的失败文案），恰两次调用、不第三次重试。"""
    llm = _ScriptedLLM([_DEGENERATE, _DEGENERATE])
    action = asyncio.run(_planner(llm, parse_retry=True)(_ctx()))

    assert action.tool_id == ""
    assert action.failed is True
    assert _PARSE_FAILED in action.args["reply"]
    assert len(llm.requests) == 2  # noqa: PLR2004 — 恰两次，无第三次


def test_retry_not_triggered_for_llm_error() -> None:
    """模型调用失败（LLMError 分支）reply 前缀不同 ⇒ 不命中失败门，不重试。"""

    class _Boom:
        def __init__(self) -> None:
            self.calls = 0

        async def acompletion(self, request: Any) -> LLMResponse:
            self.calls += 1
            raise LLMError("boom")

    boom = _Boom()
    planner = LLMPlanner(cast("Any", boom), parse_retry=True)
    action = asyncio.run(planner(_ctx()))

    assert action.failed is True
    assert "LLM 调用失败" in action.args["reply"]
    assert boom.calls == 1


def test_default_off_single_call() -> None:
    """缺省关：恰一次调用、请求不含 nudge（零回归；成因细化是门外的另一行为）。

    **不**经 `_planner` helper 传参 —— 直接构造，锚定**构造缺省**（翻缺省即红）。
    """
    llm = _ScriptedLLM([_DEGENERATE])
    action = asyncio.run(LLMPlanner(cast("Any", llm))(_ctx()))

    assert action.failed is True
    assert action.args["reply"].startswith(_PARSE_FAILED)
    assert len(llm.requests) == 1  # 无第二次请求 ⇒ 无从追加 nudge


# ── 2. 流式路径：外发门 ──────────────────────────────────────────────────────


def _collect(planner: LLMPlanner, ctx: LoopContext) -> list[str | Action]:
    async def run() -> list[str | Action]:
        return [item async for item in planner.astream(ctx)]

    return asyncio.run(run())


def test_streamed_reply_delta_not_retried() -> None:
    """已逐段外发的自然语言流（后接未闭合载荷）⇒ 不重试（不得让已见内容回滚）。"""
    streamed_failure = "先解释一下做法。\n" + _DEGENERATE
    llm = _StreamScriptedLLM([streamed_failure])
    items = _collect(_planner(llm, parse_retry=True), _ctx())

    assert len(llm.requests) == 1  # 已外发增量 ⇒ 恰一次
    terminals = [item for item in items if isinstance(item, Action)]
    assert len(terminals) == 1 and terminals[0].failed is True


def test_streamed_buffered_degenerate_retried_clean() -> None:
    """缓冲路径（首个 `{` ⇒ 全缓冲不外发）⇒ 重试，对外只有第二次的动作、零内容增量。"""
    llm = _StreamScriptedLLM([_DEGENERATE, _GOOD_ACTION])
    items = _collect(_planner(llm, parse_retry=True), _ctx())

    assert len(llm.requests) == 2  # noqa: PLR2004 — 恰两次
    assert [item for item in items if isinstance(item, str)] == []  # 第一次的退化文本不外发
    terminals = [item for item in items if isinstance(item, Action)]
    assert len(terminals) == 1  # 第一次的失败动作不 yield，只有第二次的终态
    assert terminals[0].tool_id == "tools.echo"
    assert terminals[0].failed is False


def test_streamed_good_reply_untouched() -> None:
    """正常自然语言回复流：外发增量照旧、恰一次调用（重试面零干扰）。"""
    llm = _StreamScriptedLLM([_GOOD_REPLY])
    items = _collect(_planner(llm, parse_retry=True), _ctx())

    assert "".join(item for item in items if isinstance(item, str)) == _GOOD_REPLY
    assert len(llm.requests) == 1


# ── 3. 配置三面、缺省关、非法阻断、接线 ──────────────────────────────────────

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _manager(
    tmp_path: Path, extra: str = "", *, environ: dict[str, str] | None = None
) -> ConfigManager:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    manager = ConfigManager(
        yaml_path=str(cfg), environ={"OPENAI_API_KEY": "sk-test", **(environ or {})}
    )
    manager.load()
    return manager


def test_spec_declares_parse_retry() -> None:
    """单一真源：三面齐备、缺省**关**、ADVANCED。"""
    spec = {spec.key: spec for spec in config_specs()}["loop.parse_retry"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--loop-parse-retry",
        "CORE_LOOP_PARSE_RETRY",
        False,
        "loop.parse_retry",
    )


def test_default_off_and_yaml_env_enable(tmp_path: Path) -> None:
    """缺省关；yaml / env 两面对称可达（字符串口径与 feature flag 同集）。"""
    assert _manager(tmp_path).parse_retry() is False
    assert _manager(tmp_path, "loop:\n  parse_retry: true\n").parse_retry() is True
    assert _manager(tmp_path, environ={"CORE_LOOP_PARSE_RETRY": "on"}).parse_retry() is True


def test_illegal_value_blocks_startup(tmp_path: Path) -> None:
    """`loop` 是**结构化段** ⇒ 非法取值**阻断启动**（不静默归一）。"""
    with pytest.raises(ConfigurationError, match="解析失败重试开关"):
        _manager(tmp_path, "loop:\n  parse_retry: maybe\n")


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def test_runtime_wires_parse_retry_to_main_planner(tmp_path: Path, state_dir: Path) -> None:
    """组合根把 `loop.parse_retry` 注入主 planner（与 `max_tokens`/`block_plan` 同型）。"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + "loop:\n  parse_retry: true\n", encoding="utf-8")
    runtime = build_runtime(ConfigManager(yaml_path=str(cfg)))

    assert cast("Any", runtime.loop)._planner._parse_retry is True  # noqa: SLF001 — 接线断言


def test_runtime_default_off(tmp_path: Path, state_dir: Path) -> None:
    """缺省关 ⇒ 主 planner 的重试面关（既有路径逐字不变）。"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    runtime = build_runtime(ConfigManager(yaml_path=str(cfg)))

    assert cast("Any", runtime.loop)._planner._parse_retry is False  # noqa: SLF001 — 接线断言
