"""LLM 规划器（loop 接 LLM）：上下文 + 技能 + 工具 schema → LLMRequest → Action。

替换 :class:`DefaultLoop.reason` 的 ``_echo`` 回显，把上下文装配（宪法 + 事实）、
技能提示与工具 schema 组装进统一 :class:`LLMRequest`，经
:class:`LLMProvider.completion` 推理，再把响应解析为终端回复或工具调用
:class:`Action`。解析失败返回结构化错误码，不向模型抛裸异常。

对应接口：doc/03-interfaces/loop-interface.md §3（reason 的 LLM 实现）
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from core.context import DynamicAssembler, estimate_tokens, plan_blocks
from core.llm_provider import LLMError, LLMProvider, LLMRequest, Message, TokenUsage, ToolCall
from core.tools import ToolProvider
from core.tools.env_shell import EnvironmentSnapshot, format_env_block

from .protocol import Action, ActionGroup, LoopContext, Thinking

# 解析模型输出失败时的结构化错误码（终端回复，不中断循环）。
_PARSE_FAILED = "LLM_PLAN_PARSE_FAILED"

# 不可解析原始产出的留存上界（供呈现层折叠查看与 trace 留痕；超出即截断）。见 change 0170。
_RAW_OUTPUT_MAX = 4096

# 未闭合动作载荷的可读提示（change 0170 / ADR-0161）：成因可辨时区分「被截断」与「未闭合」。
_UNPARSED_TRUNCATED = (
    f"{_PARSE_FAILED}: 输出被 provider 截断（finish_reason=length），工具调用 JSON 未闭合"
)
_UNPARSED_UNCLOSED = f"{_PARSE_FAILED}: 疑似工具调用 JSON 未闭合（输出可能被截断或写坏）"
# 夹带的动作 JSON（change 0222 / ADR-0212）：闭合的动作对象、其后仍有正文 ⇒ 可见失败
# （取代 0166/ADR-0156 的「正文中间夹带一律按回复」—— 那会把整段当答复、静默丢动作）。
_UNPARSED_EMBEDDED = f"{_PARSE_FAILED}: 动作 JSON 之后仍跟有正文（形态不可用，不执行也不当回复）"

# 命中技能提示：**纯数据**快照（loop 不 import skills —— 架构红线），由组合根组装
SkillHint = dict[str, str]  # {"skill_id": ..., "version": ..., "instructions": ...}

# 「记忆 / 事实」注入面的**字面** token 额度：区块配比未启用时的既有缺省
# （change 0201 / ADR-0191 之前为内联字面量 —— 见 `_fact_budget`）。
_FACT_BUDGET = 2048


def _format_skill_hint(hint: SkillHint) -> str:
    """渲染一条技能提示：``- <id>（<版本>）：<步骤>``；步骤为空时只留 id 与版本。"""
    head = f"- {hint['skill_id']}（{hint.get('version', '')}）"
    steps = hint.get("instructions", "").strip()
    return f"{head}：{steps}" if steps else head


_SYSTEM_PROMPT = (
    "你是 CORE-Harness 无特权核心的推理规划器，把用户任务推理为下一步动作。\n"
    "输出格式二选一，整条回复只能是其中之一（硬性互斥，须 100% 可解析）：\n"
    "①自然语言回复——用于任务已完成、无需调用工具、澄清、或文字评审/说明时；\n"
    '②JSON 工具调用——形如 {"tool_id": "...", "args": {...}}。\n'
    "选②时：JSON 必须是整条回复的**第一个字符**，其后**不得**再有任何字符"
    "（含解释、总结、结尾语、代码块围栏）；tool_id 必须取自「可用工具」列表，"
    "不得臆造；args 必须符合该工具声明的参数。\n"
    "选①时：整条只能是自然语言；**禁止**以任何形式夹杂 JSON"
    '（含 Markdown 代码块、示例、半截或完整的 {"tool_id":…}）——'
    "夹杂一律解析失败、本轮作废。解释与调工具不得写在同一条回复里。"
)

# 解析失败回喂重试的提示模板（change 0227 / ADR-0217）：**成因**（`{cause}`）＋ 输出格式
# 协议重申 ＋ 长内容分次写的用法提示 —— **绝不携带原始退化产出**（0170 纪律：raw_output
# 只进 trace/呈现；回喂退化文本会把重复模式重新注入，是自激而非纠错）。`{{`/`}}` 为
# `.format` 转义（镜像记录渲染后形态，见 prompts.md ⑮）。
_RETRY_NUDGE = (
    "你上一轮的输出无法解析为动作（{cause}），该轮作废。请重新输出并严格遵守输出格式协议："
    '整条回复只能是①自然语言回复，或②形如 {{"tool_id": …, "args": {{…}}}} 的单个 JSON 对象 —— '
    "选②时 JSON 必须是整条回复的第一个字符，其后不得再有任何字符（含解释、总结、围栏、"
    "或重复一份动作对象）；选①时禁止在正文中夹杂任何 JSON / tool_id 示例"
    "（评审说明只用自然语言）；要写入的内容较长时，请分多次、每次写一小段。"
)


def _retryable(action: Action) -> bool:
    """重试的**失败门**：解析失败（`_PARSE_FAILED` 前缀的终止动作）才命中 —— 模型调用失败
    （`LLM 调用失败` 前缀）、工具动作等一律不命中。空 `tool_id` 限定「终止动作」。"""
    reply = action.args.get("reply")
    return not action.tool_id and isinstance(reply, str) and reply.startswith(_PARSE_FAILED)


def _retry_nudge(reply: str) -> str:
    """把失败提示转成回喂消息：成因（前缀之后的部分）填入 `_RETRY_NUDGE` 模板。"""
    cause = reply.removeprefix(f"{_PARSE_FAILED}: ").strip() or "输出无法解析"
    return _RETRY_NUDGE.format(cause=cause)


def _has_word(text: str) -> bool:
    """余部是否含**词元**（字母 / 数字 / CJK）—— 「正文」与「退化残渣」的二分判据。

    change 0229 / ADR-0219：模型交出**完整可用**的动作后偶发多带一个 `}`（产出退化），
    旧判据把「一个多余 `}`」与「一整段解释正文」当成同一件事 ⇒ 0222 的形态 5 误伤、
    整轮报废零执行。判据收窄为「含词元才算正文」；纯结构符号（闭合符 / 围栏 / 标点 /
    空白）视为**残渣**、可忽略。同一谓词在 `_trailing_json_object`（要求**无**词元）与
    `_embedded_action_payload`（要求**有**词元）两处**朝向相反**地复用。
    """
    return any(ch.isalnum() for ch in text)


# 仅剥**闭合**标签残渣（不碰 ``<parameter>…</parameter>`` 对，以免破坏混写恢复）。
_TRAILING_CLOSE_MARKUP = re.compile(
    r"(?:\s*</(?:arg_value|invoke|parameter|function_calls?|tool_call|function_call"
    r"|tool_calls?|parameters?)>)+\s*$",
    re.IGNORECASE,
)
_TOOL_ID_HEAD = re.compile(r'\{\s*"tool_id"\s*:\s*"([^"]+)"')
_XML_PARAMETER = re.compile(
    r'<parameter\s+name=["\']([^"\']+)["\']\s*>(.*?)</parameter>',
    re.DOTALL | re.IGNORECASE,
)


def _strip_tool_markup_residue(text: str) -> str:
    """剥掉动作 JSON **之后**的 XML **闭合**标签残渣（如 ``</arg_value>`` / ``</invoke>``）。

    现场：完整 ``{"tool_id","args"}`` 后多带闭合标签 ⇒ 标签名含字母被 ``_has_word`` 判为正文
    ⇒ 误报「动作 JSON 之后仍跟有正文」。剥渣后余部无词元 ⇒ 按完整动作执行。
    """
    prev = None
    cleaned = text
    while prev != cleaned:
        prev = cleaned
        cleaned = _TRAILING_CLOSE_MARKUP.sub("", cleaned).rstrip()
    return cleaned


def _coerce_param_value(raw: str) -> Any:
    """``<parameter>`` 正文 → 标量：能 JSON 解码则用解码值，否则保留字符串。"""
    text = raw.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except ValueError:
        return text


def _recover_hybrid_tool_call(text: str) -> dict[str, Any] | None:
    """JSON 头 + XML ``<parameter>`` 混写 → ``{tool_id, args}``；不可恢复 ⇒ ``None``。

    现场（``~/.core/state/traces.jsonl``）：
    ``{"tool_id": "tools.file_read">\\n<parameter name="path">…</parameter>…</invoke>``
    —— 以 ``">`` 打断 JSON，后接 Anthropic 式参数标签。有 tool_id 且至少一参数才恢复。
    """
    head = _TOOL_ID_HEAD.search(text)
    if head is None:
        return None
    params = _XML_PARAMETER.findall(text)
    if not params:
        return None
    args = {name: _coerce_param_value(value) for name, value in params}
    return {"tool_id": head.group(1), "args": args}


_ACTION_META_KEYS = frozenset({"tool_id", "args", "reply"})


def _normalize_action_dict(obj: dict[str, Any]) -> dict[str, Any]:
    """扁平动作（``path`` 等与 ``tool_id`` 同级）→ 标准 ``{tool_id, args}``。"""
    tool_id = obj.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id:
        return obj
    raw_args = obj.get("args")
    args = dict(cast("dict[str, Any]", raw_args)) if isinstance(raw_args, dict) else {}
    flat = {key: value for key, value in obj.items() if key not in _ACTION_META_KEYS}
    if flat:
        args = {**args, **flat}
    return {"tool_id": tool_id, "args": args}


def _brace_close_tool_json(text: str) -> dict[str, Any] | None:
    """对未闭合 JSON 只补 ``}``（不补引号）；成功且含 args ⇒ 归一化对象。"""
    for suffix in ("}", "}}", "}}}"):
        try:
            obj = json.loads(text + suffix)
        except ValueError:
            continue
        if isinstance(obj, dict) and cast("dict[str, Any]", obj).get("tool_id"):
            normalized = _normalize_action_dict(cast("dict[str, Any]", obj))
            if normalized.get("args"):
                return normalized
    return None


def _flat_fields_from_partial_json(text: str) -> dict[str, Any]:
    """从半截扁平 JSON 抽出已闭合的字符串 / 数值字段（不含 tool_id/args/reply）。"""
    args: dict[str, Any] = {}
    for match in re.finditer(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
        key, raw = match.group(1), match.group(2)
        if key in _ACTION_META_KEYS:
            continue
        try:
            args[key] = json.loads(f'"{raw}"')
        except ValueError:
            args[key] = raw
    for match in re.finditer(r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?)(?=\s*[,}]|$)', text):
        key = match.group(1)
        if key in _ACTION_META_KEYS or key in args:
            continue
        args[key] = json.loads(match.group(2))
    return args


def _recover_truncated_tool_json(text: str) -> dict[str, Any] | None:  # noqa: PLR0911 — 多门早退
    """未闭合 / 扁平的 ``{…tool_id…}`` → 只补括号或抽**扁平**字段；不可恢复 ⇒ ``None``。

    现场（trace ``ae257340…``）：
    ``{"tool_id": "tools.file_read", "path": "…_review_planner.diff"``（缺收尾 ``}``）。

    纪律：① 已有完整首对象 ⇒ 不恢复（交给形态 5）；② 只补 ``}``、**不**补引号
    （避免半截 ``content`` 假闭合）；③ 已出现 ``"args"`` 的嵌套半截 ⇒ 不猜。
    """
    stripped = text.strip()
    if not stripped.startswith("{") or '"tool_id"' not in stripped:
        return None
    if _leading_object(stripped) is not None:
        return None
    closed = _brace_close_tool_json(stripped)
    if closed is not None:
        return closed
    if '"args"' in stripped:
        return None
    head = _TOOL_ID_HEAD.search(stripped)
    if head is None:
        return None
    args = _flat_fields_from_partial_json(stripped)
    if not args:
        return None
    return {"tool_id": head.group(1), "args": args}


def _leading_object(text: str) -> tuple[dict[str, Any], int] | None:
    """解码 ``text`` **首个**（即自首字符起的）JSON 对象，返回对象与其结束下标。

    供 `_parse` 的 `{` 开头分支做「首个对象 + 退化残渣」归一（change 0229 / ADR-0219）；
    首字符不是 `{`、或整体不可解码为非对象 ⇒ ``None``。
    """
    try:
        obj, end = json.JSONDecoder().raw_decode(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    return cast("dict[str, Any]", obj), end


def _trailing_json_object(text: str) -> dict[str, Any] | None:
    """取 ``text`` **尾部**的 JSON 对象；其后仅允许**退化残渣**（无词元的余部）。

    模型常把动作写成「解释文字 + 换行 + JSON」的混写形态（见 change 0166 / ADR-0156）：
    ``_parse`` 只认首字符 ``{`` 时，这类输出会被整段当作最终答复而**静默零执行**。
    本函数从每个 ``{`` 起试解析（``raw_decode``），只认**收在文末**的那个对象 ——
    正文中间夹带的 JSON（如解释协议时引用的示例）**不**命中，避免把「解释」当「执行」。
    余部只按 ``_has_word`` 二分（change 0229 / ADR-0219）：含词元 ⇒ 非尾部、不认；
    纯残渣（围栏 / 标点 / 空白 / 多余闭合符）⇒ 仍认，避免 0222 修掉的静默零执行回潮。
    故**不设**「文本须以 `}` 收尾」的前置门槛（承重：残渣可为纯标点，如 `…}。`）——
    否则这类输出会落到「整段当答复」的静默零执行。
    """
    tail = text.rstrip()
    if tail.endswith("```"):  # 允许 ```json … ``` 围栏收尾
        tail = tail[:-3].rstrip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(tail):
        if char != "{":
            continue
        try:
            obj, end = decoder.raw_decode(tail, index)
        except ValueError:
            continue
        if isinstance(obj, dict) and not _has_word(tail[end:]):
            return cast(dict[str, Any], obj)
    return None


def _bounded_raw(text: str) -> str:
    """原始产出的**有界**留存（超上界即截断并标记；供呈现层与 trace，不入转录/记忆）。"""
    if len(text) <= _RAW_OUTPUT_MAX:
        return text
    note = f"\n…（原始产出共 {len(text)} 字符，已截断）"
    return text[: max(0, _RAW_OUTPUT_MAX - len(note))] + note


def _never_closes(text: str, start: int) -> bool:
    """自 ``text[start]`` 起做**字符串感知**的括号深度扫描：深度**从未**回到 0 ⇒ True。

    引号内（含转义符）不计括号；深度降到 0（含负）即结构已闭合 ⇒ 立刻返回 False
    （故结束仍在字符串内 / 括号仍开 ⇒ True）。纯判定，供 `_unclosed_action_payload` 复用。
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text[start:]:
        if in_string:
            escaped = char == "\\" and not escaped
            if char == '"' and not escaped:
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            depth += 1
            continue
        if char in "}]":
            depth -= 1
            if depth <= 0:
                return False
    return True


def _unclosed_action_payload(text: str) -> bool:
    """文本尾部是否存在**到内容结束仍未闭合**的 ``"tool_id"`` 动作载荷（change 0170 / ADR-0161）。

    模型确实在**发出**动作协议、只是产出被截断或写坏时，``_trailing_json_object`` 会取到
    **内层 ``args`` 对象**（它恰好闭合且收在文末）⇒ ``tool_id`` 判空 ⇒ 旧实现把整段 JSON
    当最终答复且记为成功。本判据把这类输出识别为**不可用**。

    判据（严格，非启发式）：自**最后一次**出现的 ``"tool_id"`` 回退至其外层 ``{``，对其后文本做
    括号深度扫描（见 `_never_closes`）；深度从未回到 0 即命中。**闭合**的尾部对象 —— 不论其后
    是否仍有正文、是否含 ``tool_id`` —— 一律**不**命中（承 change 0166 的「只认尾部、宁漏勿误」）。
    """
    at = text.rfind('"tool_id"')
    if at < 0:
        return False
    start = text.rfind("{", 0, at)
    return start >= 0 and _never_closes(text, start)


def _embedded_action_payload(text: str) -> bool:
    """文本中是否存在**已闭合**的 ``"tool_id"`` 动作对象、且其后仍有正文（change 0222 / ADR-0212）。

    与 ``_trailing_json_object``（只认**收在文末**的动作对象）互补：本判据命中「完整动作协议之后
    又追加了正文」的形态 —— 旧实现把它整段当最终答复（静默零执行：动作丢失、记为成功、JSON 进
    转录与记忆）。本判据把这类输出归一为**可见失败**，与 ``_unclosed_action_payload`` 同型
    （承 change 0166/0170；**取代** ADR-0156「正文中间夹带一律按回复」的语义）。

    余部判据自 change 0229 / ADR-0219 起收窄为 ``_has_word``：余部**含词元**才算「追加了正文」；
    其后**仅**为退化残渣 ⇒ **不**命中（否则一个多余的 `}` 就会丢弃一个**完整可用**的动作，
    且 0227 的提示措辞「之后仍跟有正文」与事实不符）。
    """
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, end = decoder.raw_decode(text, index)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        payload = cast("dict[str, Any]", obj)
        if payload.get("tool_id") and _has_word(text[end:]):
            return True
    return False


class LLMPlanner:
    """ReAct 式 LLM 规划器：感知 → 装配 → 推理 → 解析 Action。"""

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        llm: LLMProvider,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        show_thinking: bool = False,
        assembler: DynamicAssembler | None = None,
        # 技能路由：``(task, session_id)``——既有 1 参闭包/替身仍可赋值（可选第二实参）
        skill_router: Callable[..., list[SkillHint]] | None = None,
        tools: ToolProvider | None = None,
        # 请求侧输出上限（由组合根按**输出预留** `loop.output_reserve` 注入 —— change 0183 /
        # ADR-0174）。`None` 或 `≤ 0` ⇒ **不**下发（请求形状逐字不变）；`> 0` ⇒ 从「记账假设」
        # 变为**端点上界**（预算派生本已假设输出至多占预留这么多）。
        max_tokens: int | None = None,
        # 上下文区块配比开关（change 0201 / ADR-0191，缺省**关**）。开启 ⇒ 装配器的注入预算
        # 由 `context.plan_blocks` 按五区块份额从 `LoopContext.token_budget` 派生；
        # 关闭 ⇒ **逐字**沿用既有字面常量（提示词零变化）。
        block_plan: bool = False,
        # 解析失败回喂重试（change 0227 / ADR-0217，缺省**关**）。开启 ⇒ 解析失败且本轮未
        # 外发内容增量时追加用户角色 nudge 重试**恰一次**；关闭 ⇒ 请求形状与调用次数逐字不变。
        parse_retry: bool = False,
        # 运行环境事实（change 0237）：注入快照或工厂 ⇒ 系统提示产「运行环境」块；
        # ``None`` ⇒ 不产块（既有提示逐字不变）。
        env_snapshot: EnvironmentSnapshot | Callable[[], EnvironmentSnapshot] | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._show_thinking = show_thinking
        self._assembler = assembler
        self._skill_router = skill_router
        self._tools = tools
        self._max_tokens = max_tokens if (max_tokens is not None and max_tokens > 0) else None
        self._block_plan = block_plan
        self._parse_retry = parse_retry
        self._env_snapshot = env_snapshot
        # 最近一次装配的提示 token 观测（记账下界）：由 `last_prompt_tokens()` 对外暴露，
        # 供 loop 侧以 duck-typing 探针消费（见 change 0152 / 账本 E96）。
        self._last_prompt_tokens = 0
        # 最近一次流式响应实报的**完成**用量（纯观测面：不参与终止语义与预算闸门 ——
        # 本轮已花出的量无可行动作；见 change 0183 / ADR-0174）。
        self._last_completion_tokens = 0

    async def __call__(self, ctx: LoopContext) -> Action | ActionGroup:
        action, _ = await self._complete(ctx)
        return action

    async def _complete(self, ctx: LoopContext) -> tuple[Action | ActionGroup, str]:
        """非流式一次补全 →（终态动作, 推理原文）。``__call__`` 与降级分支共用。

        解析失败回喂重试（change 0227 / ADR-0217）：门开且命中失败判据 ⇒ 追加 nudge **恰
        再试一次**（非流式路径本就不外发增量 ⇒ 恒可重试）；仍失败 ⇒ 第二次的结果即终态。
        """
        action, thinking = await self._complete_once(ctx)
        if self._parse_retry and isinstance(action, Action) and _retryable(action):
            action, thinking = await self._complete_once(
                ctx, nudge=_retry_nudge(action.args["reply"])
            )
        return action, thinking

    async def _complete_once(
        self, ctx: LoopContext, *, nudge: str = ""
    ) -> tuple[Action | ActionGroup, str]:
        """一次非流式补全（不带重试门；`_complete` 负责恰一次重试）。"""
        request = self._build_request(ctx)
        if nudge:
            request.messages.append(Message(role="user", content=nudge))
        self._last_prompt_tokens = self._estimate_prompt(request)
        try:
            response = await self._llm.acompletion(request)
        except LLMError as exc:
            return Action(args={"reply": f"LLM 调用失败: {exc}"}, failed=True), ""
        # provider 实报为**下界**：可用时抬升（实测权威；不因估算偏差而低估提示词占用）
        self._last_prompt_tokens = max(self._last_prompt_tokens, response.usage.prompt_tokens)
        if response.tool_calls:  # 原生 function call 优先于 content 协议
            return self._from_tool_calls(response.tool_calls), response.thinking
        return (
            self._parse(response.content, finish_reason=response.finish_reason),
            response.thinking,
        )

    async def astream(
        self, ctx: LoopContext
    ) -> AsyncIterator[str | Action | ActionGroup | Thinking]:
        """流式推理：自然语言回复逐 delta 外发，末态产出终 Action。

        首个 ``{`` 判定为工具调用 JSON：缓冲不外泄（逐 token 外发半截 JSON 无意义），
        拼完整后走 ``_parse``；原生 tool_calls 片段按 index 累积（name/arguments），
        同样缓冲不外发。provider 不支持流式（缺 astream）或流式失败时与
        ``__call__`` 同语义（终端回复，不抛裸异常）。

        思考回显开启（``show_thinking``）时**额外**外发 ``Thinking`` 增量；关闭时该
        分支整体不产出（事件面与既有缺省逐字一致）。

        解析失败回喂重试（change 0227 / ADR-0217）：**缓冲路径**（未外发任何内容增量）
        的解析失败 ⇒ 第一次的终态不外发、回喂重试**恰一次**（对外只有第二次的产出）；
        已外发内容增量（自然语言流）⇒ 不重试（不得让已见内容「回滚」）。
        """
        if not hasattr(self._llm, "astream"):
            # 降级分支的重试由 `_complete` 承担（同一门；非流式本就不外发增量）
            action, thinking = await self._complete(ctx)  # completion-only provider
            if self._show_thinking and thinking:
                yield Thinking(thinking)  # 终态思考一次性全文（先于终态动作）
            yield action
            return
        streamed_content = False  # 外发门：内容增量一旦外发即不可重试
        async for item in self._stream_attempt(ctx):
            if isinstance(item, str):
                streamed_content = True
                yield item
                continue
            if (
                isinstance(item, Action)
                and not streamed_content
                and self._parse_retry
                and _retryable(item)
            ):
                # 缓冲路径的解析失败：吞掉第一次的终态，回喂重试恰一次（对外零痕迹）
                async for retry_item in self._stream_attempt(
                    ctx, nudge=_retry_nudge(item.args["reply"])
                ):
                    yield retry_item
                return
            yield item

    async def _stream_attempt(  # noqa: C901 — 长管道：回复增量 + 原生工具片段 + 思考增量
        self, ctx: LoopContext, *, nudge: str = ""
    ) -> AsyncIterator[str | Action | ActionGroup | Thinking]:
        """一次流式推理尝试（不带重试门；外发门与恰一次重试由 ``astream`` 承担）。"""
        request = self._build_request(ctx)
        if nudge:
            request.messages.append(Message(role="user", content=nudge))
        self._last_prompt_tokens = self._estimate_prompt(request)
        chunks: list[str] = []
        reply_stream = False  # 已判定为自然语言回复才外发
        native_tool = False  # 出现原生 tool_calls 片段
        tool_names: dict[int, str] = {}
        tool_args: dict[int, str] = {}
        # 终止原因（change 0170）：末个非空值胜出，用于把「被截断」与「未闭合」区分开。
        # `getattr` 取值：第三方 provider 若产出自有形块（无该字段），退化为空串、不破。
        finish_reason = ""
        try:
            async for chunk in self._llm.astream(request):
                # 用量消费**早于** `continue` 闸门：端点把用量放在 `content` 为空的末块上
                # （change 0183 / ADR-0174）⇒ 放在 `if not chunk.content: continue` 之后会漏掉。
                self._observe_usage(getattr(chunk, "usage", None))
                finish_reason = getattr(chunk, "finish_reason", "") or finish_reason
                for fragment in chunk.tool_calls or []:
                    native_tool = True
                    index = fragment.index
                    tool_names[index] = tool_names.get(index, "") or fragment.tool_id
                    tool_args[index] = tool_args.get(index, "") + fragment.arguments
                if self._show_thinking and chunk.thinking:
                    yield Thinking(chunk.thinking)  # 纯思考增量的 chunk 无 content，先行外发
                if not chunk.content:
                    continue
                chunks.append(chunk.content)
                if len(chunks) == 1 and not native_tool:
                    reply_stream = not chunk.content.lstrip().startswith("{")
                if reply_stream and not native_tool:
                    yield chunk.content
        except LLMError as exc:
            yield Action(args={"reply": f"LLM 调用失败: {exc}"}, failed=True)
            return
        if native_tool:
            calls = [
                ToolCall(
                    tool_id=tool_names[index],
                    arguments=tool_args[index],
                    index=index,
                )
                for index in sorted(tool_names)
            ]
            yield self._from_tool_calls(calls)
            return
        yield self._parse("".join(chunks), finish_reason=finish_reason)

    def last_prompt_tokens(self) -> int:
        """最近一次装配的提示 token 观测（记账**下界**；尚未推理过时为 0）。

        取「装配全量估算」与「provider 实报 ``usage.prompt_tokens``」的较大者：估算覆盖
        **装配进提示词的全部内容**（全部消息 + 工具 schema），实报为权威数字、只会抬升。
        loop 侧经 ``getattr(planner, "last_prompt_tokens", None)`` 探针消费（与 ``astream``
        同型 duck-typing），使预算闸门看得见系统提示与工具 schema。
        """
        return self._last_prompt_tokens

    def last_completion_tokens(self) -> int:
        """最近一次响应实报的**完成** token 数（**观测面**；未上报时为 0）。

        与 ``last_prompt_tokens()`` 同型 duck-typing 探针。**不参与**任何判定 —— 预算闸门看的是
        下一轮的提示词占用，本轮已花出的完成量无可行动作（见 change 0183 / ADR-0174）。
        """
        return self._last_completion_tokens

    def _observe_usage(self, usage: TokenUsage | None) -> None:
        """消费一次实报用量：提示词占用取**较大者**（下界只抬升、从不压低），完成量记观测。

        ``None``（该块未报用量）⇒ 原样返回（第三方 provider 产出自有形块时不破，与
        ``finish_reason`` 的 ``getattr`` 处置同型）。
        """
        if usage is None:
            return
        self._last_prompt_tokens = max(self._last_prompt_tokens, usage.prompt_tokens)
        self._last_completion_tokens = usage.completion_tokens

    @staticmethod
    def _estimate_prompt(request: LLMRequest) -> int:
        """装配全量估算：全部消息内容 + 工具 schema 序列化。

        口径同共享估计器 ``context.estimate_tokens``（``len // 4``，每条至少 1）。
        """
        total = sum(estimate_tokens(message.content) for message in request.messages)
        if request.tools:
            total += estimate_tokens(json.dumps(request.tools, ensure_ascii=False))
        return total

    def _build_request(self, ctx: LoopContext) -> LLMRequest:
        # 次序：系统提示 → 本会话历史 → 本轮消息（历史走**独立字段**，不掺进 ctx.messages）
        messages = [Message(role="system", content=self._system_prompt(ctx))]
        messages.extend(self._to_messages(ctx.history))
        messages.extend(self._to_messages(ctx.messages))
        return LLMRequest(
            messages=messages,
            model=self._model or "",
            max_tokens=self._max_tokens,
            tools=self._tool_schemas(),
            reasoning_effort=self._reasoning_effort,
        )

    # ---- 组装 ----

    def _fact_budget(self, ctx: LoopContext) -> int:
        """「记忆 / 事实」注入面的 token 额度。

        区块配比**关闭**（缺省）或本轮预算未接线（`ctx.token_budget` ≤ 0）⇒ 既有字面常量
        （提示词逐字不变）；开启且预算为正 ⇒ `plan_blocks` 的**记忆份额**
        （change 0201 / ADR-0191 —— loop 预算由此首次到达 planner）。
        """
        plan = plan_blocks(ctx.token_budget, enabled=self._block_plan)
        return plan.memory_tokens if plan is not None else _FACT_BUDGET

    def _system_prompt(self, ctx: LoopContext) -> str:  # noqa: C901 — 块装配多分支长管道
        # （与 `default.py::astream` 同口径：分支数随块种类线性增长，拆函数反而割裂块装配单点）
        blocks: list[str] = [_SYSTEM_PROMPT]
        # 装配器调用提到块外：常驻笔记注入**不依赖**装配器（缺省未装装配器亦须每轮在场）
        pack = (
            self._assembler.build(
                self._task(ctx),
                stage="reason",
                budget=self._fact_budget(ctx),
                session_id=ctx.session_id,
            )
            if self._assembler is not None
            else None
        )
        if pack is not None and pack.constitution:
            blocks.append("宪法规则：\n" + "\n".join(f"- {line}" for line in pack.constitution))
        # 常驻笔记：任务级硬约束锚 —— **独立块**（不折入「相关笔记」），紧随宪法规则、先于其余块。
        # 无条件（与 query 命中无关），故判据只看本字段是否非空。
        if ctx.pinned_notes.strip():
            blocks.append(
                "常驻笔记（任务级硬约束，逐轮生效，勿违背）：\n" + ctx.pinned_notes.strip()
            )
        # 分层历史摘要：**独立块**（不折入「相关事实」/历史消息），长层先于中层（change 0178）。
        # 空字段不产块 ⇒ 未分层时 prompt 逐字不变。
        if ctx.summary_long.strip():
            blocks.append("历史摘要（长期）：\n" + ctx.summary_long.strip())
        if ctx.summary_mid.strip():
            blocks.append("历史摘要（中期）：\n" + ctx.summary_mid.strip())
        if pack is not None and pack.facts:
            blocks.append(
                "相关事实：\n" + "\n".join(f"- [{f['source']}] {f['content']}" for f in pack.facts)
            )
        if pack is not None and pack.pointers:
            blocks.append(
                "文档目录（按需取详情，勿请求全文）：\n"
                + "\n".join(f"- {p['pointer']}：{p['summary']}" for p in pack.pointers)
            )
        if ctx.notes.strip():
            blocks.append("相关笔记：\n" + ctx.notes.strip())
        # 既往失败教训：本会话失败条目的**有界**注入（change 0217 / ADR-0207）—— **独立块**，
        # 缺省空 ⇒ 不产块 ⇒ 提示词**逐字不变**。不折入「相关事实」（后者按预算截断、会静默丢弃），
        # 也不折入「相关笔记」（语义不同）。
        if ctx.failure_lessons.strip():
            blocks.append("既往失败教训：\n" + ctx.failure_lessons.strip())
        # 后台任务完成通知：轮首一次性投递的**独立块**（change 0270 / ADR-0260）—— 缺省空
        # ⇒ 不产块、提示词逐字不变；不折入其他块（瞬态协调信号，非知识）。
        if ctx.notices.strip():
            blocks.append("后台任务通知：\n" + ctx.notices.strip())
        skills = self._skill_hints(self._task(ctx), ctx.session_id)
        if skills:
            blocks.append("可用技能：\n" + "\n".join(_format_skill_hint(s) for s in skills))
        env_block = self._env_block()
        if env_block:
            blocks.append(env_block)
        if self._tools is not None:
            schemas = [f"- {t.tool_id}: {t.description}" for t in self._tools.active_tools()]
            blocks.append("可用工具：\n" + "\n".join(schemas))
        return "\n\n".join(blocks)

    def _env_block(self) -> str:
        """运行环境事实块；未注入 ⇒ 空串（不产块）。"""
        raw = self._env_snapshot
        if raw is None:
            return ""
        snap = raw() if callable(raw) else raw
        return "运行环境：\n" + format_env_block(snap)

    def _tool_schemas(self) -> list[Any] | None:
        if self._tools is None:
            return None
        # OpenAI 兼容工具信封：端点按 function.name 校验，裸参数 schema 会被拒（400）
        return [
            {
                "type": "function",
                "function": {
                    "name": t.tool_id,
                    "description": t.description,
                    "parameters": t.schema,
                },
            }
            for t in self._tools.active_tools()
        ]

    def _skill_hints(self, task: str, session_id: str = "") -> list[SkillHint]:
        """技能路由提示；``session_id`` 非空才作第二实参（既有 1 参闭包/替身调用形态不变）。"""
        if self._skill_router is None:
            return []
        if session_id:
            return self._skill_router(task, session_id)
        return self._skill_router(task)

    @staticmethod
    def _task(ctx: LoopContext) -> str:
        if not ctx.messages:
            return ""
        first = ctx.messages[0]
        if isinstance(first, dict):
            return str(cast(dict[str, Any], first).get("content", ""))
        return str(first)

    @staticmethod
    def _to_messages(messages: list[Any]) -> list[Message]:
        result: list[Message] = []
        for raw in messages:
            role, content = "user", str(raw)
            if isinstance(raw, dict):
                role = str(cast(dict[str, Any], raw).get("role", "user"))
                content = str(cast(dict[str, Any], raw).get("content", ""))
            if role not in ("system", "user", "assistant", "tool"):
                role = "user"
            result.append(
                Message(
                    role=role,
                    content=content,
                )
            )
        return result

    # ---- 解析 ----

    def _parse(  # noqa: PLR0911,C901 — 五种形态 + 空/首字符分支，逐形态早返更清晰
        self, content: str, *, finish_reason: str = ""
    ) -> Action:
        raw = content.strip()
        if not raw:
            return Action(args={"reply": f"{_PARSE_FAILED}: 空响应"}, failed=True)
        # JSON 头 + <parameter> 混写：在剥渣**之前**恢复（否则尾部 </parameter> 会被剥掉）
        recovered = _recover_hybrid_tool_call(raw)
        if recovered is not None:
            return self._from_dict(recovered)
        # 剥 XML 闭合残渣，避免 </arg_value> 被 ``_has_word`` 当成「正文」
        text = _strip_tool_markup_residue(raw)
        if text.startswith("{"):
            # 形态 2 容残渣（change 0229 / ADR-0219）：首个对象完整、其后**仅**退化残渣
            # （无词元）⇒ 按该对象处理（`{"reply": …}` 亦然，避免「同一谓词、两种朝向、
            # 三种结论」的新不对称）。余部含词元 ⇒ 落到下方既有路径（成因措辞逐字不变）。
            leading = _leading_object(text)
            if leading is not None and not _has_word(text[leading[1] :]):
                return self._from_dict(leading[0])
            try:
                data = json.loads(text)
            except ValueError:
                repaired = _recover_truncated_tool_json(text)
                if repaired is not None:
                    return self._from_dict(repaired)
                return Action(
                    args={"reply": self._first_brace_reply(text, finish_reason)},
                    raw_output=_bounded_raw(raw),
                    failed=True,
                )
            return self._from_dict(data)
        # 混写形态（正文 + 尾部动作 JSON）容错：见 change 0166 / ADR-0156。
        # 只认尾部、且只认**动作**形态（含非空 tool_id）；其余与既有实现逐字一致。
        embedded = _trailing_json_object(text)
        if embedded is not None and embedded.get("tool_id"):
            return self._from_dict(embedded)
        # 未闭合但可补全的扁平动作（与 `{` 分支同口径）
        repaired = _recover_truncated_tool_json(text)
        if repaired is not None:
            return self._from_dict(repaired)
        # 未闭合的动作载荷（change 0170 / ADR-0161）：模型在**发出**动作协议，只是产出被截断/写坏
        # —— 旧实现会把整段 JSON 当答复且记为成功（静默 + JSON 进转录与记忆）。
        if _unclosed_action_payload(text):
            reply = _UNPARSED_TRUNCATED if finish_reason == "length" else _UNPARSED_UNCLOSED
            return Action(args={"reply": reply}, raw_output=_bounded_raw(raw), failed=True)
        # 夹带的动作 JSON（change 0222 / ADR-0212）：闭合的动作对象之后仍有正文 ⇒ 可见失败
        # （旧实现整段当答复 ⇒ 静默零执行；本判据**取代** ADR-0156「中间夹带一律按回复」）。
        if _embedded_action_payload(text):
            return Action(
                args={"reply": _UNPARSED_EMBEDDED},
                raw_output=_bounded_raw(raw),
                failed=True,
            )
        return Action(args={"reply": text})

    @staticmethod
    def _first_brace_reply(text: str, finish_reason: str) -> str:
        """`{` 开头但整体不可解析时的失败提示：复用形态 4/5 判据区分成因（change 0227）。

        只改提示信息量（失败语义、有界原始产出均不变）：命中未闭合载荷判据 ⇒ 按
        `finish_reason` 区分截断/未闭合（与形态 4 同文）；命中夹带判据（含**对象在前、
        正文在后**的形态）⇒ 形态 5 措辞；皆不命中 ⇒ 通用文案（逐字）。事故形态
        （trace `1c7cfb24…`：缺收尾 `}` ＋ 重复对象 ＋ 截断）在此前只有通用文案。
        """
        if _unclosed_action_payload(text):
            return _UNPARSED_TRUNCATED if finish_reason == "length" else _UNPARSED_UNCLOSED
        if _embedded_action_payload(text):
            return _UNPARSED_EMBEDDED
        return f"{_PARSE_FAILED}: 无法解析模型输出为动作"

    def _from_tool_calls(self, calls: list[ToolCall]) -> Action | ActionGroup:
        """原生 tool_calls → Action / ActionGroup（多调用**全量**映射，change 0257）。

        单调用仍返回 ``Action``（既有协议与断言逐字不变）；多调用按 provider ``index``
        升序返回 ``ActionGroup``。任一调用非法 ⇒ 整个批次归一为**单个**失败终止动作
        （``LLM_PLAN_PARSE_FAILED``），零部分执行 —— 部分执行会让模型看到的工具结果与它
        发出的调用数量不一致。
        """
        actions: list[Action] = []
        for call in sorted(calls, key=lambda item: item.index):
            action = self._from_tool_call(call)
            if action.failed:
                return action
            actions.append(action)
        if len(actions) == 1:
            return actions[0]
        return ActionGroup(actions=actions)

    def _from_tool_call(self, call: ToolCall) -> Action:
        """单个原生调用 → Action；非法时返回失败终止动作（由批次映射归一整体失败）。"""
        if not call.tool_id:
            return Action(args={"reply": f"{_PARSE_FAILED}: 工具调用缺 function.name"}, failed=True)
        try:
            args = json.loads(call.arguments or "{}")
        except ValueError:
            return Action(args={"reply": f"{_PARSE_FAILED}: 工具参数无法解析为 JSON"}, failed=True)
        if not isinstance(args, dict):
            return Action(args={"reply": f"{_PARSE_FAILED}: 工具参数非 JSON 对象"}, failed=True)
        return Action(
            tool_id=call.tool_id,
            args=cast(dict[str, Any], args),
            is_irreversible=self._is_irreversible(call.tool_id),
        )

    def _from_dict(self, data: Any) -> Action:
        if not isinstance(data, dict):
            return Action(args={"reply": f"{_PARSE_FAILED}: 模型输出非 JSON 对象"}, failed=True)
        obj = _normalize_action_dict(cast("dict[str, Any]", data))
        tool_id = obj.get("tool_id")
        if tool_id:
            raw_args = obj.get("args")
            args = cast(dict[str, Any], raw_args) if isinstance(raw_args, dict) else {}
            return Action(
                tool_id=str(tool_id),
                args=args,
                is_irreversible=self._is_irreversible(str(tool_id)),
            )
        reply = obj.get("reply")
        if reply is not None:
            return Action(args={"reply": str(reply)})
        return Action(args={"reply": f"{_PARSE_FAILED}: 对象缺 tool_id/reply"}, failed=True)

    def _is_irreversible(self, tool_id: str) -> bool:
        if self._tools is None:
            return False
        for tool in self._tools.active_tools():
            if tool.tool_id == tool_id:
                is_write = any("write" in c for c in tool.coeffects)
                return is_write and not tool.reversible
        return False
