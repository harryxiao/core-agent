"""TaskHandoff 统一执行框架（orchestration）。

调度器、beast、pet 三条执行路径共用本模块：构建有界上下文包、渲染交接输入、
按 deadline 执行子 Agent。``orchestration`` 不 import ``beast`` / ``pet`` ——
依赖方向保持「上层复用编排层」。

对应接口：doc/03-interfaces/orchestration-interface.md §3
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

from core.loop import LoopEvent, LoopPlugin, LoopResult
from core.tokens import estimate_tokens

from .errors import OrchestrationError, OrchestrationErrorCode
from .models import TaskHandoff

# 单字段字符上界（与调度器既有交接口径同值；change 0247）
MAX_HANDOFF_CHARS = 2000
# 上下文包总预算（粗略 token 估算；CJK 感知，见 core.tokens）
DEFAULT_CONTEXT_TOKENS = 2000


def _clip(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars]


def _fit_tokens(text: str, max_tokens: int) -> str:
    """按估算 token 截断（保留前缀；预算非正 ⇒ 空串）。"""
    while text and max_tokens > 0 and estimate_tokens(text) > max_tokens:
        text = text[: len(text) * 3 // 4]
    return text if max_tokens > 0 else ""


def build_context_pack(
    goal: str,
    dependencies: list[tuple[str, str, str]],
    *,
    max_tokens: int,
) -> dict[str, Any]:
    """构建有界上下文包：``{"goal", "dependencies": [{"id","goal","result"}]}``。

    按依赖顺序装入；每条先扣 id/goal 头部预算，结果按剩余预算截断；
    任一条被截断即停止装入（后续依赖不再进包）。单条字段另受
    ``MAX_HANDOFF_CHARS`` 上界。
    """
    pack: dict[str, Any] = {
        "goal": _clip(goal, MAX_HANDOFF_CHARS),
        "dependencies": [],
    }
    used = estimate_tokens(str(pack["goal"]))
    for dep_id, dep_goal, result in dependencies:
        clipped_goal = _clip(dep_goal, MAX_HANDOFF_CHARS)
        head = f"[{dep_id}] {clipped_goal}"
        budget = max_tokens - used - estimate_tokens(head)
        if budget <= 0:
            break
        raw = _clip(result, MAX_HANDOFF_CHARS)
        fitted = _fit_tokens(raw, budget)
        pack["dependencies"].append({"id": dep_id, "goal": clipped_goal, "result": fitted})
        used += estimate_tokens(head) + estimate_tokens(fitted)
        if fitted != raw:
            break
    return pack


def render_handoff(handoff: TaskHandoff) -> str:
    """渲染交接输入：``task`` + 原始目标 + 前置结果 + 验收标准。

    上下文为空且无验收标准时**逐字返回 ``task``** ⇒ beast / pet 既有行为不变。
    """
    if not handoff.context_pack and not handoff.acceptance:
        return handoff.task
    lines = [handoff.task]
    goal = str(handoff.context_pack.get("goal") or "")
    if goal:
        lines.append(f"\n[原始目标] {goal}")
    raw_deps = handoff.context_pack.get("dependencies")
    dependencies = cast("list[dict[str, Any]]", raw_deps) if isinstance(raw_deps, list) else []
    if dependencies:
        lines.append("\n[前置子任务结果]")
        lines.extend(
            f"- {entry.get('id', '')}: {entry.get('result', '')}" for entry in dependencies
        )
    if handoff.acceptance:
        lines.append(f"\n[验收标准] {handoff.acceptance}")
    return "\n".join(lines)


def _deadline_error(deadline: float) -> OrchestrationError:
    return OrchestrationError(
        OrchestrationErrorCode.SUBTASK_TIMEOUT,
        f"交接超时（{deadline:g}s）",
    )


async def stream_handoff(
    loop: LoopPlugin, handoff: TaskHandoff, *, deadline: float | None = None
) -> AsyncIterator[LoopEvent]:
    """流式执行交接；``deadline``（秒）非空且 >0 时整体限时。"""
    prompt = render_handoff(handoff)
    stream = (
        loop.astream(prompt, session_id=handoff.session_id)
        if handoff.session_id
        else loop.astream(prompt)
    )
    if deadline is None or deadline <= 0:
        async for event in stream:
            yield event
        return
    try:
        async with asyncio.timeout(deadline):
            async for event in stream:
                yield event
    except TimeoutError as exc:
        raise _deadline_error(deadline) from exc


async def run_handoff(
    loop: LoopPlugin, handoff: TaskHandoff, *, deadline: float | None = None
) -> LoopResult:
    """收口执行交接（经 ``arun``，保留后台收尾语义）；超时归一 ``SUBTASK_TIMEOUT``。"""
    prompt = render_handoff(handoff)
    if deadline is None or deadline <= 0:
        return await _arun(loop, prompt, handoff.session_id)
    try:
        async with asyncio.timeout(deadline):
            return await _arun(loop, prompt, handoff.session_id)
    except TimeoutError as exc:
        raise _deadline_error(deadline) from exc


async def _arun(loop: LoopPlugin, prompt: str, session_id: str) -> LoopResult:
    if session_id:
        return await loop.arun(prompt, session_id=session_id)
    return await loop.arun(prompt)
