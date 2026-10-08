"""0166 · 推理输出协议容错与失败可见（承 ADR-0156）。

事故：模型回了**完全正确**的动作 JSON，但形态是「解释文字 + 换行 + JSON」⇒ 旧 `_parse`
以首字符判定 ⇒ 整段当答复 ⇒ 零执行、零报错，且本轮记为成功。

本文件覆盖两侧：**尾部动作 JSON 的识别**（容错）与**解析失败 ⇒ 本轮失败**（可见）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.llm_provider import LLMError, LLMResponse, TokenUsage
from core.loop import Action, DefaultLoop, LLMPlanner, LoopContext, LoopResult
from core.loop.planner import _RAW_OUTPUT_MAX
from core.memory import MemoryEntry
from core.tools import Tool, ToolDef, ToolProvider

# 事故现场的最小复刻：正文（解释）在前、动作 JSON 在尾部
_PROSE = "执行提交（先 add 再 commit，然后归档 + 复跑 validate，一气呵成但分步验证）：\n\n"
_ACTION = '{"tool_id": "tools.echo", "args": {"text": "hi"}}'


def _echo_tool() -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="tools.echo",
            description="echo",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=[],
            reversible=True,
        ),
        handler=lambda text: f"echo:{text}",
    )


class _FakeLLM:
    """按序出内容的假 LLM（单个字符串 ⇒ 恒定；列表 ⇒ 逐个消费，末项重复）。"""

    def __init__(self, content: str | list[str]) -> None:
        self._queue = [content] if isinstance(content, str) else list(content)

    def completion(self, request: Any) -> LLMResponse:
        return LLMResponse(
            content=self._queue.pop(0) if len(self._queue) > 1 else self._queue[0],
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="fake",
            model="test-model",
        )

    async def acompletion(self, request: Any) -> LLMResponse:
        return self.completion(request)


class _BoomLLM:
    """调用即失败的假 LLM（模型调用不可用）。"""

    def completion(self, request: Any) -> LLMResponse:
        raise LLMError("boom")

    async def acompletion(self, request: Any) -> LLMResponse:
        return self.completion(request)


def _parse(content: str) -> Action:
    provider = ToolProvider()
    provider.register(_echo_tool())
    planner = LLMPlanner(_FakeLLM(content), tools=provider)
    return asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "hi"}])))


# ---- ① 尾部动作 JSON：识别（容错） ----


def test_trailing_action_json_after_prose_is_tool_call() -> None:
    """事故复刻：正文 + 尾部动作 JSON ⇒ 工具动作（不得当答复）。"""
    action = _parse(_PROSE + _ACTION)
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    assert not action.is_terminal
    assert action.failed is False


def test_fenced_trailing_action_json_is_tool_call() -> None:
    """围栏包裹的尾部动作 JSON ⇒ 同样识别为工具动作。"""
    action = _parse(_PROSE + "```json\n" + _ACTION + "\n```")
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}


def test_action_json_mid_text_stays_reply() -> None:
    """正文**中间**夹带的动作 JSON（如解释协议）⇒ 仍是答复（只认尾部，宁漏勿误）。"""
    content = "输出格式二选一：①自然语言回复；②JSON 工具调用 " + _ACTION + " —— 就这样。"
    action = _parse(content)
    assert action.is_terminal
    assert action.args["reply"] == content
    assert action.failed is False


def test_trailing_json_without_tool_id_stays_reply() -> None:
    """文末 JSON 无 `tool_id`（如示例配置）⇒ 仍是答复。"""
    content = '建议把上限调成这样：\n\n{"max_rounds": 3, "token_budget": 8000}'
    action = _parse(content)
    assert action.is_terminal
    assert action.args["reply"] == content
    assert action.failed is False


def test_plain_text_reply_unchanged() -> None:
    """普通文本答复：逐字零回归，且不标记失败。"""
    action = _parse("直接回复文本")
    assert action.args == {"reply": "直接回复文本"}
    assert action.is_terminal
    assert action.failed is False


def test_pure_json_action_path_unchanged() -> None:
    """纯 JSON 动作路径零回归。"""
    action = _parse(_ACTION)
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    assert action.failed is False


# ---- ② 失败可见：解析失败 / 模型调用失败 ⇒ 失败态 ----


def test_truncated_json_marks_action_failed() -> None:
    action = _parse('{"tool_id": "tools.echo",')
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert action.failed is True


def test_empty_content_marks_action_failed() -> None:
    action = _parse("   ")
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert action.failed is True


def test_object_without_tool_id_or_reply_marks_action_failed() -> None:
    action = _parse('{"args": {}}')
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert action.failed is True


def test_llm_error_marks_action_failed() -> None:
    planner = LLMPlanner(_BoomLLM())
    action = asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "hi"}])))
    assert "LLM 调用失败" in action.args["reply"]
    assert action.failed is True


# ---- ③ 端到端：失败态终止动作 ⇒ 本轮失败（收尾钩子同口径） ----


class _RecordingMemory:
    """记录写入条目的记忆替身（只关心沉淀结果，参照 test_loop.py）。"""

    def __init__(self) -> None:
        self.written: list[MemoryEntry] = []

    def read(self, query: str, budget: int = 0) -> list[MemoryEntry]:
        return []

    def write(self, layer: str, entry: MemoryEntry) -> str:
        self.written.append(entry)
        return entry.id


def _run_with(content: str | list[str]) -> tuple[LoopResult, list[bool], list[str]]:
    seen: list[bool] = []
    calls: list[str] = []
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=_echo_tool().definition,
            handler=lambda text: calls.append(text) or f"echo:{text}",
        )
    )
    loop = DefaultLoop(
        planner=LLMPlanner(_FakeLLM(content), tools=provider),
        tools=provider,
        turn_observer=lambda task, steps, ok: seen.append(ok),
    )
    return loop.run("hi"), seen, calls


def test_parse_failure_marks_turn_failed() -> None:
    """解析失败 ⇒ LoopResult.failed=True 且收尾钩子收到 ok=False（不得记成功）。"""
    result, seen, _ = _run_with('{"tool_id": "tools.echo",')
    assert result.failed is True
    assert "LLM_PLAN_PARSE_FAILED" in result.reply
    assert seen == [False]


def test_normal_turn_not_marked_failed() -> None:
    """正常轮：失败标记与收尾钩子零回归。"""
    result, seen, _ = _run_with("直接回复文本")
    assert result.failed is False
    assert result.reply == "直接回复文本"
    assert seen == [True]


def test_trailing_action_json_executes_in_loop() -> None:
    """事故复刻的端到端：尾部动作 JSON ⇒ 工具**真的**执行（旧实现零执行）。"""
    result, seen, calls = _run_with([_PROSE + _ACTION, "完成"])
    assert calls == ["hi"]  # 工具确实被调用（旧实现此处为空）
    assert result.reply == "完成"
    assert result.failed is False
    assert seen == [True]


# ---- ④ 形态 4：未闭合的动作载荷（change 0170 / ADR-0161）----

# 事故轮的最小复刻：外层动作对象**未闭合**，文本止于内层字符串（内层 args 恰好闭合
# ⇒ 旧 `_trailing_json_object` 会把**参数块**当「尾部对象」返回，`tool_id` 判空后整段当正文）。
_UNCLOSED = _PROSE + '{"tool_id": "tools.file_write", "args": {"path": "a.md", "content": "未写完'


def test_unclosed_action_payload_marks_failed() -> None:
    """未闭合的动作载荷 ⇒ 失败态终止动作；`reply` 为可读提示，**不含**原始 JSON。"""
    action = _parse(_UNCLOSED)
    assert action.is_terminal
    assert action.failed is True
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert '"tool_id"' not in action.args["reply"]  # 不得把 JSON 当正文
    assert action.raw_output  # 原始产出另路留存（有界）
    assert "tools.file_write" in action.raw_output


def test_unclosed_action_payload_raw_output_is_bounded() -> None:
    """原始产出有界：超长输入只留上界内前缀。"""
    huge = _PROSE + '{"tool_id": "tools.file_write", "args": {"content": "' + "甲" * 9000
    action = _parse(huge)
    assert action.failed is True
    assert 0 < len(action.raw_output) <= _RAW_OUTPUT_MAX


def test_closed_tail_object_without_tool_id_stays_reply() -> None:
    """形态 4 的反面守护：**闭合**的尾部对象 ⇒ 仍是答复（承 0166「只认尾部、宁漏勿误」）。"""
    closed = '建议这样调：\n\n{"tool_id": "tools.echo", "args": {"text": "hi"}} 就这样。'
    action = _parse(closed)
    assert action.is_terminal
    assert action.args["reply"] == closed
    assert action.failed is False
    assert action.raw_output == ""


def test_unclosed_payload_finish_reason_length_distinguishes_cause() -> None:
    """成因可辨：provider 报 `length` ⇒ 提示明示「截断」；信号缺省 ⇒ 「未闭合」（失败语义相同）。"""
    provider = ToolProvider()
    planner = LLMPlanner(_FakeLLM("x"), tools=provider)
    truncated = planner._parse(_UNCLOSED, finish_reason="length")
    unclosed = planner._parse(_UNCLOSED)
    assert "截断" in truncated.args["reply"]
    # 「未闭合」措辞**允许**把截断列为疑似成因（规格 形态 4），但不得声称 provider 报告了截断。
    assert "finish_reason" not in unclosed.args["reply"]
    assert truncated.args["reply"] != unclosed.args["reply"]
    assert truncated.failed is True and unclosed.failed is True


def test_unclosed_action_payload_keeps_raw_out_of_persisted_surfaces() -> None:
    """端到端：本轮失败可见，原始产出**不进**回复与记忆沉淀（只经 LoopResult 可见）。"""
    memory = _RecordingMemory()
    loop = DefaultLoop(planner=LLMPlanner(_FakeLLM(_UNCLOSED)), memory=memory)  # type: ignore[arg-type]
    result = loop.run("hi")
    assert result.failed is True
    assert '"tool_id"' not in result.reply  # 正文只留可读提示
    assert "tools.file_write" in result.raw_output  # 原始产出另路可诊断
    persisted = "\n".join(entry.content for entry in memory.written)
    assert '"tool_id"' not in persisted  # 红线：不进转录 / 记忆 / 笔记
