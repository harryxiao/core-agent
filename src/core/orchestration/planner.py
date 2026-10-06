"""LLM 拆解 / 验收适配器（orchestration）。

LLMSubtaskPlanner：目标 → 子任务 DAG（经 llm-provider acompletion 单轮 JSON）；
LLMVerifier：验收门（对照子任务 acceptance 判定结果真伪）。拆解失败或输出
不可解析回落单子任务（任务不中断）；验收判定失败 fail-closed（不静默放行）。

对应接口：doc/03-interfaces/orchestration-interface.md §2.1
"""

from __future__ import annotations

import json
from typing import Any, cast

from core.llm_provider import LLMError, LLMProvider, LLMRequest, Message

from .models import Subtask, VerifyResult

_DECOMPOSE_SYSTEM = (
    "你是任务拆解器。把目标拆成 2-6 个可执行的子任务 DAG，"
    '仅输出 JSON：{"subtasks": [{"id": "1", "goal": "...", '
    '"acceptance": "...", "depends_on": [], "priority": 0, "difficulty": "medium"}]}。'
    "规则：goal 是给执行智能体的单一明确指令；acceptance 是可判定的验收标准；"
    "depends_on 只引用已声明的 id，无依赖则留空数组；无依赖子任务不要伪造依赖；"
    'difficulty 是该子任务的难易度，只能取 "easy" / "medium" / "hard" 三档之一，'
    "把握不足时取 medium。"
)

_VERIFY_SYSTEM = (
    "你是验收判定器。对照验收标准判定子任务结果是否达标，"
    '仅输出 JSON：{"passed": true, "reason": "..."}。'
    "结果未提供、与标准无关或未达标准时判 false，并给出一句话理由。"
)

_MAX_VERIFY_CHARS = 4000  # 验收判定输入截断（结果正文有界）


def _extract_json(text: str) -> Any:
    """剥围栏与前后噪声后解析 JSON；失败返回 None（不抛裸异常）。"""
    stripped = text.strip()
    if stripped.startswith("```"):  # ```json ... ``` 围栏
        stripped = stripped.strip("`").lstrip("json").strip()
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(stripped[start : end + 1])
    except ValueError:
        return None


class LLMSubtaskPlanner:
    """LLM 子任务拆解器：目标 → 子任务 DAG；失败/不可解析回落单子任务。"""

    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def __call__(self, goal: str) -> list[Subtask]:
        request = LLMRequest(
            messages=[
                Message(role="system", content=_DECOMPOSE_SYSTEM),
                Message(role="user", content=f"目标：{goal}"),
            ],
            model=self._model or "",
        )
        try:
            response = await self._llm.acompletion(request)
        except LLMError:
            return self._fallback(goal)
        subtasks = self._parse(response.content)
        return subtasks if subtasks else self._fallback(goal)

    def _parse(self, content: str) -> list[Subtask]:
        """逐项校验模型输出（id/goal 非空、depends_on 引用已声明 id），非法项剔除。"""
        data = _extract_json(content)
        if isinstance(data, dict):
            data = cast(dict[str, Any], data).get("subtasks")
        if not isinstance(data, list):
            return []
        entries = cast(list[Any], data)
        items = [cast(dict[str, Any], item) for item in entries if isinstance(item, dict)]
        ids = {
            str(item.get("id", "")).strip()
            for item in items
            if str(item.get("id", "")).strip() and str(item.get("goal", "")).strip()
        }
        subtasks: list[Subtask] = []
        for item in items:
            sid = str(item.get("id", "")).strip()
            sgoal = str(item.get("goal", "")).strip()
            if not sid or not sgoal:
                continue
            raw_deps = item.get("depends_on")
            depends_on = (
                [str(dep) for dep in cast(list[Any], raw_deps) if str(dep) in ids]
                if isinstance(raw_deps, list)
                else []
            )
            raw_priority = item.get("priority", 0)
            subtasks.append(
                Subtask(
                    id=sid,
                    goal=sgoal,
                    acceptance=str(item.get("acceptance", "")),
                    depends_on=depends_on,
                    priority=raw_priority if isinstance(raw_priority, int) else 0,
                    # 弱信号：集合外取值由 `Subtask.__post_init__` 归一为 medium（不剔除子任务）
                    difficulty=item.get("difficulty", ""),
                )
            )
        return subtasks

    @staticmethod
    def _fallback(goal: str) -> list[Subtask]:
        """回落单子任务：目标整体交执行循环（多轮工具调用仍可推进）。"""
        return [Subtask(id="1", goal=goal, acceptance="")]


def _as_bool(value: Any) -> bool | None:
    """判定字段归一：bool 直取；"true"/"false" 字符串归一（模型偶发引号包裹）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


class LLMVerifier:
    """LLM 验收门：对照 acceptance 判定结果；调用失败/不可解析 fail-closed。"""

    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def __call__(self, subtask: Subtask, result: Any) -> VerifyResult:
        text = str(result or "").strip()
        request = LLMRequest(
            messages=[
                Message(role="system", content=_VERIFY_SYSTEM),
                Message(
                    role="user",
                    content=(
                        f"子任务：{subtask.goal}\n"
                        f"验收标准：{subtask.acceptance}\n"
                        f"结果：{text[:_MAX_VERIFY_CHARS]}"
                    ),
                ),
            ],
            model=self._model or "",
        )
        # 单次重试容忍偶发空响应/不可解析输出；重试仍失败按 fail-closed 不放行
        verdict = await self._judge(request)
        if verdict is None:
            verdict = await self._judge(request)
        return verdict if verdict is not None else self._fail_closed()

    async def _judge(self, request: LLMRequest) -> VerifyResult | None:
        """单次判定：可解析返回判定；调用失败/不可解析返回 None（可重试）。"""
        try:
            response = await self._llm.acompletion(request)
        except LLMError:
            return None
        data = _extract_json(response.content)
        if not isinstance(data, dict):
            return None
        verdict = cast(dict[str, Any], data)
        passed = _as_bool(verdict.get("passed"))
        if passed is None:
            return None
        reason = str(verdict.get("reason", "")).strip()
        if not reason:
            reason = "验收通过" if passed else "未达验收标准"
        return VerifyResult(passed=passed, reason=reason)

    @staticmethod
    def _fail_closed() -> VerifyResult:
        return VerifyResult(
            passed=False, reason="验收判定失败（fail-closed）: 输出不可解析或调用失败"
        )
