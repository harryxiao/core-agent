"""退化 JSON 的转义与内引号修复（change 0321 / ADR-0311）。

事故（trace ``a36c6cff…``，2026-10-24 14:14）：子 Agent 交出的动作对象结构完整，但
字符串内的双引号未转义、``\\|`` 是非法 JSON 转义 ⇒ ``json.loads`` 失败、既有恢复链
均不命中 ⇒ 整轮「无法解析」。本文件钉恢复与**不越界**两侧：只有结构完整、修复后可
解码为动作 / 回复对象的形态才采纳；未闭合与无动作字段的形态维持可见失败。
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.llm_provider import LLMResponse, TokenUsage
from core.loop import Action, LLMPlanner, LoopContext
from core.tools import ToolProvider

# 事故原文复刻：内层 "memory…" 等引号未转义，\| 为非法 JSON 转义。
_INCIDENT = (
    r'{"tool_id": "tools.code_run", "args": {"script": "cd ~/work/core-agent && '
    r'ls tests/ | grep -i "memory\|write\|deactiv" ; '
    r'grep -n "write_checked\|WriteRejection" src/core/memory/store.py"}}'
)

_SCRIPT = (
    'cd ~/work/core-agent && ls tests/ | grep -i "memory\\|write\\|deactiv" ; '
    'grep -n "write_checked\\|WriteRejection" src/core/memory/store.py'
)


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def completion(self, request: Any) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="fake",
            model="test-model",
        )

    async def acompletion(self, request: Any) -> LLMResponse:
        return self.completion(request)


def _parse(content: str) -> Action:
    planner = LLMPlanner(_FakeLLM(content), tools=ToolProvider())
    return asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "hi"}])))


def test_unescaped_quotes_and_invalid_escapes_recover() -> None:
    """事故复刻：结构完整、仅字面量写坏 ⇒ 工具动作，文本逐字保留。"""
    action = _parse(_INCIDENT)

    assert action.failed is False
    assert action.tool_id == "tools.code_run"
    assert action.args["script"] == _SCRIPT


def test_unclosed_payload_does_not_get_repaired() -> None:
    """未闭合 / 截断形态不享受修复：不猜缺的括号，维持失败语义。"""
    action = _parse(r'{"tool_id": "tools.file_read", "args": {"path": "a"b')

    assert action.failed is True
    assert str(action.args["reply"]).startswith("LLM_PLAN_PARSE_FAILED")


def test_repaired_object_without_action_or_reply_is_not_adopted() -> None:
    """修复后可解码但无 tool_id / reply ⇒ 不采纳，维持通用失败文案。"""
    action = _parse(r'{"hello": "a"b"}')

    assert action.failed is True
    assert action.args["reply"] == "LLM_PLAN_PARSE_FAILED: 无法解析模型输出为动作"


def test_valid_json_with_escapes_is_unchanged() -> None:
    """合法 JSON（含转义引号 / 反斜杠）走既有路径，解码值逐字不变。"""
    action = _parse(r'{"tool_id": "tools.echo", "args": {"text": "say \"hi\" and \\|"}}')

    assert action.failed is False
    assert action.tool_id == "tools.echo"
    assert action.args["text"] == 'say "hi" and \\|'
