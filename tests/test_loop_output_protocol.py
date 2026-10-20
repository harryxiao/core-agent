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

    def __init__(self, content: str | list[str], finish_reason: str = "stop") -> None:
        self._queue = [content] if isinstance(content, str) else list(content)
        self._finish_reason = finish_reason

    def completion(self, request: Any) -> LLMResponse:
        return LLMResponse(
            content=self._queue.pop(0) if len(self._queue) > 1 else self._queue[0],
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason=self._finish_reason,
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


def _parse(content: str, *, finish_reason: str = "stop") -> Action:
    provider = ToolProvider()
    provider.register(_echo_tool())
    planner = LLMPlanner(_FakeLLM(content, finish_reason=finish_reason), tools=provider)
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


def test_action_json_mid_text_now_fails_visibly() -> None:
    """正文中间夹带的**动作** JSON（含非空 tool_id、其后仍有正文）⇒ **可见失败**。

    见 change 0222 / ADR-0212。

    **取代**旧语义（change 0166 / ADR-0156「只认尾部、宁漏勿误」）：旧实现把「完整动作协议 + 尾随
    正文」整段当最终答复 ⇒ **静默零执行**（动作丢失、记为成功、JSON 进转录与记忆）。新语义把它
    归一为一次**可见**的解析失败 —— 代价（偶发误伤「解释协议时引用动作 JSON」的回复）低于静默丢失。
    """
    content = "输出格式二选一：①自然语言回复；②JSON 工具调用 " + _ACTION + " —— 就这样。"
    action = _parse(content)
    assert action.is_terminal
    assert action.failed is True
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert "tool_id" not in action.args["reply"]
    assert action.raw_output == content


def test_embedded_action_json_is_not_executed() -> None:
    """夹带的动作 JSON **不得被执行**（形态 5 是失败态，不是工具动作）。"""
    content = _PROSE + _ACTION + "\n我读一下这个文件。"
    action = _parse(content)
    assert action.tool_id == ""
    assert action.is_terminal
    assert action.failed is True


def test_embedded_non_action_json_mid_text_stays_reply() -> None:
    """正文中夹带**无** tool_id 的示例 JSON ⇒ 仍是答复（不误伤解释/示例）。"""
    content = '配置示例：{"max_rounds": 3, "token_budget": 8000} 就这样。'
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


def test_empty_content_with_length_reports_truncation() -> None:
    """空内容 + finish_reason=length ⇒ 明示截断/预算可能被思考耗尽（change 0292）。"""
    action = _parse("   ", finish_reason="length")
    assert action.tool_id == ""
    assert action.failed is True
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert "空响应" in action.args["reply"]
    assert "截断" in action.args["reply"]
    assert "max_tokens" in action.args["reply"]


def test_empty_content_without_length_keeps_exact_wording() -> None:
    """无截断信号（stop / 缺失）⇒ 空响应文案逐字不变（change 0292）。"""
    for reason in ("stop", ""):
        action = _parse("", finish_reason=reason)
        assert action.failed is True
        assert action.args["reply"] == "LLM_PLAN_PARSE_FAILED: 空响应"


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
        turn_observer=lambda task, steps, ok, reply: seen.append(ok),
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


def test_closed_action_object_with_trailing_prose_is_embedded_failure() -> None:
    """形态 5 守护：**闭合**的动作对象之后仍有正文 ⇒ **可见失败**（取代 0166 的「宁漏勿误」）。

    旧语义（ADR-0156）下本例整段当答复 ⇒ **静默零执行**；新语义（change 0222 / ADR-0212）归一为
    失败态终止动作。**形态 4**（未闭合载荷）仍**不**命中**闭合**对象 —— 二者判据互斥、各有守护。
    """
    closed = '建议这样调：\n\n{"tool_id": "tools.echo", "args": {"text": "hi"}} 就这样。'
    action = _parse(closed)
    assert action.is_terminal
    assert action.failed is True
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert action.raw_output == closed


def test_trailing_xml_arg_value_residue_still_executes() -> None:
    """完整 JSON 后仅跟 ``</arg_value>`` 等工具协议残渣 ⇒ 仍按动作执行（非「正文」）。

    现场（traces.jsonl）：合法 ``{"tool_id","args"}`` 后多了 ``</arg_value>``，旧判据
    ``_has_word`` 把标签名当词元 ⇒ 误报「动作 JSON 之后仍跟有正文」。
    """
    content = (
        '{"tool_id": "tools.code_run", "args": {"script": "echo hi", "type": "bash"}}</arg_value>'
    )
    action = _parse(content)
    assert action.failed is False
    assert action.tool_id == "tools.code_run"
    assert action.args["script"] == "echo hi"


# ---- ⑤ 动作 JSON + 纯 JSON 注释（change 0297 / ADR-0287）----

# 事故现场（trace fc82601b…）：完整动作后跟一个无动作语义的分析对象。
_ANNOTATION = '\n,{"integrated_analysis": ["目录不存在", "工作区有未提交修改"]}'


def test_action_json_with_trailing_annotation_object_executes() -> None:
    """动作后跟纯 JSON 注释对象 ⇒ 执行首动作，注释不进入 args/reply。"""
    action = _parse(_ACTION + _ANNOTATION)
    assert action.failed is False
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    assert action.raw_output == ""


def test_action_json_with_trailing_annotation_array_executes() -> None:
    """注释值可为数组（或标量）—— 同一结构判据。"""
    action = _parse(_ACTION + '\n["note", 1, true]')
    assert action.failed is False
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}


def test_action_json_with_trailing_second_action_still_fails() -> None:
    """动作后跟第二个动作 ⇒ 维持形态 5 可见失败，不静默丢弃第二个动作。"""
    second = '{"tool_id": "tools.echo", "args": {"text": "second"}}'
    action = _parse(_ACTION + "\n" + second)
    assert action.is_terminal
    assert action.failed is True
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]
    assert action.raw_output


def test_action_json_with_trailing_reply_object_still_fails() -> None:
    """动作后跟 reply 对象 ⇒ 无法判定本轮终态，维持形态 5。"""
    action = _parse(_ACTION + '\n{"reply": "done"}')
    assert action.is_terminal
    assert action.failed is True
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]


def test_action_json_with_annotation_then_prose_still_fails() -> None:
    """注释序列之后再跟正文 ⇒ 不是纯 JSON 注释序列，维持形态 5。"""
    action = _parse(_ACTION + _ANNOTATION + "\n完成")
    assert action.is_terminal
    assert action.failed is True
    assert "动作 JSON 之后仍跟有正文" in action.args["reply"]


def test_hybrid_json_head_plus_xml_parameters_recovers() -> None:
    """JSON 头被 ``">`` 打断 + ``<parameter>`` 混写 ⇒ 恢复为可执行动作。

    现场（trace ``69100bfe…`` raw_output）：
    ``{"tool_id": "tools.file_read">\\n<parameter name="path">…</parameter>…</invoke>``
    """
    content = (
        '{"tool_id": "tools.file_read">\n'
        '<parameter name="path">D:\\work\\AI\\core-agent\\src\\core\\llm_provider'
        "\\stdlib_provider.py</parameter>\n"
        '<parameter name="start">1</parameter>\n'
        '<parameter name="count">120</parameter>\n'
        "</invoke>"
    )
    action = _parse(content)
    assert action.failed is False
    assert action.tool_id == "tools.file_read"
    assert action.args["path"].endswith("stdlib_provider.py")
    assert action.args["start"] == 1  # noqa: PLR2004 — 数值参数应 JSON 强制
    assert action.args["count"] == 120  # noqa: PLR2004


def test_flat_and_truncated_file_read_json_recovers() -> None:
    """扁平 + 缺收尾 ``}`` 的 file_read ⇒ 仍恢复为 ``args.path``。

    现场（trace ``ae257340…``，重启后新失败）：
    ``{"tool_id": "tools.file_read", "path": "…_review_planner.diff"``
    （无 ``args`` 包裹、字符串未闭合对象）。
    """
    content = (
        '{"tool_id": "tools.file_read", "path": '
        '"D:\\\\work\\\\AI\\\\core-agent\\\\_review_planner.diff"'
    )
    action = _parse(content)
    assert action.failed is False
    assert action.tool_id == "tools.file_read"
    assert action.args["path"].endswith("_review_planner.diff")


def test_flat_complete_tool_json_hoists_into_args() -> None:
    """完整但扁平的动作对象（字段与 tool_id 同级）⇒ 抬入 ``args``。"""
    content = '{"tool_id": "tools.file_read", "path": "a.py", "start": 1}'
    action = _parse(content)
    assert action.failed is False
    assert action.tool_id == "tools.file_read"
    assert action.args == {"path": "a.py", "start": 1}


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


# ---- ④ `{` 开头失败的成因细化（change 0227 / ADR-0217）----
#
# 事故形态（trace 1c7cfb24…）：`{` 开头、缺最外层收尾 `}`（或闭合对象后仍有重复正文）
# ⇒ 首字符分支整体 json.loads 失败 ⇒ 旧实现只给通用文案。形态 4/5 的判据本就覆盖
# 同根因输出，此处把判据接进该分支（复用、零新启发式），只改提示信息量。


def test_brace_first_unclosed_distinguishes_cause_by_finish_reason() -> None:
    """`{` 开头未闭合载荷：length ⇒ 截断措辞；信号缺省 ⇒ 未闭合措辞（失败语义相同）。"""
    provider = ToolProvider()
    planner = LLMPlanner(_FakeLLM("x"), tools=provider)
    degenerate = '{"tool_id": "tools.file_write", "args": {"path": "a.md", "content": "x'
    truncated = planner._parse(degenerate, finish_reason="length")
    unclosed = planner._parse(degenerate)
    assert "截断" in truncated.args["reply"]
    assert "未闭合" in unclosed.args["reply"]
    assert truncated.args["reply"] != unclosed.args["reply"]
    assert truncated.failed is True and unclosed.failed is True
    assert truncated.raw_output and unclosed.raw_output  # 有界原始产出照旧


def test_brace_first_closed_object_then_prose_names_cause() -> None:
    """`{` 开头、闭合动作对象后仍有正文（事故的重复对象形态）⇒ EMBEDDED 措辞。"""
    action = _parse('{"tool_id": "tools.echo", "args": {"text": "hi"}} 已完成上述写入。')
    assert "动作 JSON 之后仍跟有正文" in action.args["reply"]
    assert action.failed is True
    assert action.raw_output


def test_brace_first_no_discriminator_keeps_generic_wording() -> None:
    """`{` 开头但既无未闭合载荷、亦无夹带动作对象 ⇒ 通用文案逐字（零回归锚）。"""
    action = _parse('{"hello": "world", broken')
    assert action.args["reply"] == "LLM_PLAN_PARSE_FAILED: 无法解析模型输出为动作"
    assert action.failed is True


# ---- ⑤ 退化残渣不等于「追加正文」（change 0229 / ADR-0219）----
#
# 事故（trace 6925d31f…，2026-10-12 08:25）：模型交出一个**完整可用**的动作 JSON，末尾只多出
# **一个孤零零的 `}`** ⇒ `json.loads` 报 `Extra data` ⇒ 「形态 5」把它误判为「动作 JSON 之后仍
# 跟有正文」⇒ 整轮报废、**零执行**（且 `loop.parse_retry` 缺省关 ⇒ 无补救）。
#
# 判据收窄：余部**含词元**（字母/数字/CJK）才算「正文」；**仅**结构性残渣（无词元：多余闭合符 /
# 围栏符 / 零散标点 / 空白）⇒ 残渣可忽略、动作照常执行。同一谓词两处朝向相反
# （`_embedded_action_payload` 要求含词元；`_trailing_json_object` 要求无词元）。

# 事故现场的最小复刻：**完整**的 file_write 动作（1806 字符正文压成短串，结构不变）
_INCIDENT = (
    '{"tool_id": "tools.file_write", "args": {"path": "~/x/proposal.md", '
    '"content": "# Proposal\\n\\n## Why\\n\\n一段正文。"}}'
)


def test_action_json_with_trailing_stray_brace_executes() -> None:
    """事故复刻：完整动作 JSON + 末尾多出的一个 `}` ⇒ **工具动作**（不得整轮报废）。"""
    action = _parse(_INCIDENT + "}")
    assert action.tool_id == "tools.file_write"
    assert action.args["path"] == "~/x/proposal.md"
    assert action.args["content"].startswith("# Proposal")
    assert action.is_terminal is False
    assert action.failed is False
    assert action.raw_output == ""  # 未发生解析失败 ⇒ 无原始产出留存


def test_action_json_with_trailing_punctuation_or_fence_residue_executes() -> None:
    """围栏符 / 零散标点 / 多余空白残渣 ⇒ 一律按工具动作执行（残渣二分：无词元）。"""
    for residue in ("\n```", "。", " }}", "\n\n", " ;"):
        action = _parse(_INCIDENT + residue)
        assert action.tool_id == "tools.file_write", residue
        assert action.failed is False, residue


def test_prose_then_action_then_residue_executes() -> None:
    """「正文 + 动作 JSON + 残渣」⇒ 执行 —— 尾部对象判据同步收窄（否则会**落回整段当答复**）。"""
    action = _parse(_PROSE + _ACTION + "}")
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    assert action.failed is False


def test_prose_then_action_then_punctuation_residue_executes() -> None:
    """残渣**不以 `}` 收尾**（纯标点，形态 3 路径）⇒ 仍执行 —— 余部判据无「须以 `}` 收尾」门槛。

    承重：若 `_trailing_json_object` 保留该门槛，本例会落到**整段当答复**的**静默零执行**
    （`_embedded` 已收窄、不命中）—— 即 0222 / ADR-0212 修掉的那类。
    """
    action = _parse(_PROSE + _ACTION + "。")
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    assert action.failed is False


def test_action_json_then_worded_text_still_fails() -> None:
    """边界锚：其后跟随**含词元**的正文 ⇒ 形态 5 **语义不变**（可见失败、不执行）。"""
    action = _parse(_INCIDENT + "\n已完成写入。")
    assert action.is_terminal
    assert action.failed is True
    assert "动作 JSON 之后仍跟有正文" in action.args["reply"]
    assert action.raw_output  # 有界原始产出照旧
