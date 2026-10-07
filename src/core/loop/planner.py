"""LLM 规划器（loop 接 LLM）：上下文 + 技能 + 工具 schema → LLMRequest → Action。

替换 :class:`DefaultLoop.reason` 的 ``_echo`` 回显，把上下文装配（宪法 + 事实）、
技能提示与工具 schema 组装进统一 :class:`LLMRequest`，经
:class:`LLMProvider.completion` 推理，再把响应解析为终端回复或工具调用
:class:`Action`。解析失败返回结构化错误码，不向模型抛裸异常。

对应接口：doc/03-interfaces/loop-interface.md §3（reason 的 LLM 实现）
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from core.context import DynamicAssembler, estimate_tokens
from core.llm_provider import LLMError, LLMProvider, LLMRequest, Message, ToolCall
from core.tools import ToolProvider

from .protocol import Action, LoopContext, Thinking

# 解析模型输出失败时的结构化错误码（终端回复，不中断循环）。
_PARSE_FAILED = "LLM_PLAN_PARSE_FAILED"

# 命中技能提示：**纯数据**快照（loop 不 import skills —— 架构红线），由组合根组装
SkillHint = dict[str, str]  # {"skill_id": ..., "version": ..., "instructions": ...}


def _format_skill_hint(hint: SkillHint) -> str:
    """渲染一条技能提示：``- <id>（<版本>）：<步骤>``；步骤为空时只留 id 与版本。"""
    head = f"- {hint['skill_id']}（{hint.get('version', '')}）"
    steps = hint.get("instructions", "").strip()
    return f"{head}：{steps}" if steps else head


_SYSTEM_PROMPT = (
    "你是 CORE-Harness 无特权核心的推理规划器，把用户任务推理为下一步动作。\n"
    '输出格式二选一：①自然语言回复；②JSON 工具调用 {"tool_id": "...", "args": {...}}。'
)


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
    ) -> None:
        self._llm = llm
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._show_thinking = show_thinking
        self._assembler = assembler
        self._skill_router = skill_router
        self._tools = tools
        # 最近一次装配的提示 token 观测（记账下界）：由 `last_prompt_tokens()` 对外暴露，
        # 供 loop 侧以 duck-typing 探针消费（见 change 0152 / 账本 E96）。
        self._last_prompt_tokens = 0

    async def __call__(self, ctx: LoopContext) -> Action:
        action, _ = await self._complete(ctx)
        return action

    async def _complete(self, ctx: LoopContext) -> tuple[Action, str]:
        """非流式一次补全 →（终态动作, 推理原文）。``__call__`` 与降级分支共用。"""
        request = self._build_request(ctx)
        self._last_prompt_tokens = self._estimate_prompt(request)
        try:
            response = await self._llm.acompletion(request)
        except LLMError as exc:
            return Action(args={"reply": f"LLM 调用失败: {exc}"}), ""
        # provider 实报为**下界**：可用时抬升（实测权威；不因估算偏差而低估提示词占用）
        self._last_prompt_tokens = max(self._last_prompt_tokens, response.usage.prompt_tokens)
        if response.tool_calls:  # 原生 function call 优先于 content 协议
            return self._from_tool_calls(response.tool_calls), response.thinking
        return self._parse(response.content), response.thinking

    async def astream(  # noqa: C901 — 长管道：降级分支 + 回复增量 + 原生工具片段 + 思考增量
        self, ctx: LoopContext
    ) -> AsyncIterator[str | Action | Thinking]:
        """流式推理：自然语言回复逐 delta 外发，末态产出终 Action。

        首个 ``{`` 判定为工具调用 JSON：缓冲不外泄（逐 token 外发半截 JSON 无意义），
        拼完整后走 ``_parse``；原生 tool_calls 片段按 index 累积（name/arguments），
        同样缓冲不外发。provider 不支持流式（缺 astream）或流式失败时与
        ``__call__`` 同语义（终端回复，不抛裸异常）。

        思考回显开启（``show_thinking``）时**额外**外发 ``Thinking`` 增量；关闭时该
        分支整体不产出（事件面与既有缺省逐字一致）。
        """
        if not hasattr(self._llm, "astream"):
            action, thinking = await self._complete(ctx)  # completion-only provider
            if self._show_thinking and thinking:
                yield Thinking(thinking)  # 终态思考一次性全文（先于终态动作）
            yield action
            return
        request = self._build_request(ctx)
        self._last_prompt_tokens = self._estimate_prompt(request)
        chunks: list[str] = []
        reply_stream = False  # 已判定为自然语言回复才外发
        native_tool = False  # 出现原生 tool_calls 片段
        tool_names: dict[int, str] = {}
        tool_args: dict[int, str] = {}
        try:
            async for chunk in self._llm.astream(request):
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
            yield Action(args={"reply": f"LLM 调用失败: {exc}"})
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
        yield self._parse("".join(chunks))

    def last_prompt_tokens(self) -> int:
        """最近一次装配的提示 token 观测（记账**下界**；尚未推理过时为 0）。

        取「装配全量估算」与「provider 实报 ``usage.prompt_tokens``」的较大者：估算覆盖
        **装配进提示词的全部内容**（全部消息 + 工具 schema），实报为权威数字、只会抬升。
        loop 侧经 ``getattr(planner, "last_prompt_tokens", None)`` 探针消费（与 ``astream``
        同型 duck-typing），使预算闸门看得见系统提示与工具 schema。
        """
        return self._last_prompt_tokens

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
            tools=self._tool_schemas(),
            reasoning_effort=self._reasoning_effort,
        )

    # ---- 组装 ----

    def _system_prompt(self, ctx: LoopContext) -> str:
        blocks: list[str] = [_SYSTEM_PROMPT]
        # 装配器调用提到块外：常驻笔记注入**不依赖**装配器（缺省未装装配器亦须每轮在场）
        pack = (
            self._assembler.build(
                self._task(ctx), stage="reason", budget=2048, session_id=ctx.session_id
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
        skills = self._skill_hints(self._task(ctx), ctx.session_id)
        if skills:
            blocks.append("可用技能：\n" + "\n".join(_format_skill_hint(s) for s in skills))
        if self._tools is not None:
            schemas = [f"- {t.tool_id}: {t.description}" for t in self._tools.active_tools()]
            blocks.append("可用工具：\n" + "\n".join(schemas))
        return "\n\n".join(blocks)

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

    def _parse(self, content: str) -> Action:
        text = content.strip()
        if not text:
            return Action(args={"reply": f"{_PARSE_FAILED}: 空响应"})
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except ValueError:
                return Action(args={"reply": f"{_PARSE_FAILED}: 无法解析模型输出为动作"})
            return self._from_dict(data)
        return Action(args={"reply": text})

    def _from_tool_calls(self, calls: list[ToolCall]) -> Action:
        """原生 tool_calls → Action（Action 为单工具协议，并行多调用取首个）。"""
        first = calls[0]
        if not first.tool_id:
            return Action(args={"reply": f"{_PARSE_FAILED}: 工具调用缺 function.name"})
        try:
            args = json.loads(first.arguments or "{}")
        except ValueError:
            return Action(args={"reply": f"{_PARSE_FAILED}: 工具参数无法解析为 JSON"})
        if not isinstance(args, dict):
            return Action(args={"reply": f"{_PARSE_FAILED}: 工具参数非 JSON 对象"})
        return Action(
            tool_id=first.tool_id,
            args=cast(dict[str, Any], args),
            is_irreversible=self._is_irreversible(first.tool_id),
        )

    def _from_dict(self, data: Any) -> Action:
        if not isinstance(data, dict):
            return Action(args={"reply": f"{_PARSE_FAILED}: 模型输出非 JSON 对象"})
        obj = cast(dict[str, Any], data)
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
        return Action(args={"reply": f"{_PARSE_FAILED}: 对象缺 tool_id/reply"})

    def _is_irreversible(self, tool_id: str) -> bool:
        if self._tools is None:
            return False
        for tool in self._tools.active_tools():
            if tool.tool_id == tool_id:
                is_write = any("write" in c for c in tool.coeffects)
                return is_write and not tool.reversible
        return False
