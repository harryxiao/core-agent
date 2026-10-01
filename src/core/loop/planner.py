"""LLM 规划器（loop 接 LLM）：上下文 + 技能 + 工具 schema → LLMRequest → Action。

替换 :class:`DefaultLoop.reason` 的 ``_echo`` 回显，把上下文装配（宪法 + 事实）、
技能提示与工具 schema 组装进统一 :class:`LLMRequest`，经
:class:`LLMProvider.completion` 推理，再把响应解析为终端回复或工具调用
:class:`Action`。解析失败返回结构化错误码，不向模型抛裸异常。

对应接口：doc/03-interfaces/loop-interface.md §3（reason 的 LLM 实现）
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

from core.context import DynamicAssembler
from core.llm_provider import LLMError, LLMProvider, LLMRequest, Message
from core.tools import ToolProvider

from .protocol import Action, LoopContext

# 解析模型输出失败时的结构化错误码（终端回复，不中断循环）。
_PARSE_FAILED = "LLM_PLAN_PARSE_FAILED"

_SYSTEM_PROMPT = (
    "你是 CORE-Harness 无特权核心的推理规划器，把用户任务推理为下一步动作。\n"
    '输出格式二选一：①自然语言回复；②JSON 工具调用 {"tool_id": "...", "args": {...}}。'
)


class LLMPlanner:
    """ReAct 式 LLM 规划器：感知 → 装配 → 推理 → 解析 Action。"""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        model: str | None = None,
        assembler: DynamicAssembler | None = None,
        skill_router: Callable[[str], list[str]] | None = None,
        tools: ToolProvider | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._assembler = assembler
        self._skill_router = skill_router
        self._tools = tools

    async def __call__(self, ctx: LoopContext) -> Action:
        request = self._build_request(ctx)
        try:
            response = await self._llm.acompletion(request)
        except LLMError as exc:
            return Action(args={"reply": f"LLM 调用失败: {exc}"})
        return self._parse(response.content)

    def _build_request(self, ctx: LoopContext) -> LLMRequest:
        messages = [Message(role="system", content=self._system_prompt(ctx))]
        messages.extend(self._to_messages(ctx.messages))
        return LLMRequest(
            messages=messages,
            model=self._model or "",
            tools=self._tool_schemas(),
        )

    # ---- 组装 ----

    def _system_prompt(self, ctx: LoopContext) -> str:
        blocks: list[str] = [_SYSTEM_PROMPT]
        if self._assembler is not None:
            pack = self._assembler.build(self._task(ctx), stage="reason", budget=2048)
            if pack.constitution:
                blocks.append("宪法规则：\n" + "\n".join(f"- {line}" for line in pack.constitution))
            if pack.facts:
                blocks.append(
                    "相关事实：\n"
                    + "\n".join(f"- [{f['source']}] {f['content']}" for f in pack.facts)
                )
        skills = self._skill_hints(self._task(ctx))
        if skills:
            blocks.append("可用技能：\n" + "\n".join(f"- {skill}" for skill in skills))
        if self._tools is not None:
            schemas = [f"- {t.tool_id}: {t.description}" for t in self._tools.active_tools()]
            blocks.append("可用工具：\n" + "\n".join(schemas))
        return "\n\n".join(blocks)

    def _tool_schemas(self) -> list[Any] | None:
        if self._tools is None:
            return None
        return [t.schema for t in self._tools.active_tools()]

    def _skill_hints(self, task: str) -> list[str]:
        if self._skill_router is None:
            return []
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
