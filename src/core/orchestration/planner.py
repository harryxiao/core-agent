"""LLM 拆解 / 验收适配器（orchestration）。

LLMSubtaskPlanner：目标 → 子任务 DAG（经 llm-provider acompletion 单轮 JSON）；
LLMVerifier：验收门（对照子任务 acceptance 判定结果真伪）。拆解失败或输出
不可解析回落单子任务（任务不中断）；验收判定失败 fail-closed（不静默放行）。

对应接口：doc/03-interfaces/orchestration-interface.md §2.1
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from core.llm_provider import LLMError, LLMProvider, LLMRequest, Message
from core.memory.extract import redact_secrets

from .models import DecomposeResult, Subtask, VerifyResult

if TYPE_CHECKING:
    from .scheduler import SubtaskOutcome

_DECOMPOSE_SYSTEM = (
    "你是任务拆解器。把目标拆成 1-6 个可执行的子任务 DAG，"
    '仅输出 JSON：{"success_criteria": ["..."], "subtasks": [{"id": "1", "goal": "...", '
    '"acceptance": "...", "depends_on": [], "priority": 0, "difficulty": "medium"}]}。'
    "success_criteria 是整体目标的成功标准：2-5 条、每条可客观判定真伪"
    "（如「测试全部通过」「文件 X 存在且含 Y」），覆盖整体目标，不要复述子任务的 acceptance；"
    "规则：goal 是给执行智能体的单一明确指令，且须**自包含**——执行者看不到原始目标，"
    "所需背景、路径与约束都要写进 goal；acceptance 是可判定的验收标准，须能被客观检查"
    "（如「测试通过」「文件 X 含 Y」），不要写「质量好」「尽量」这类无法判定的表述；"
    "depends_on 只引用已声明的 id，无依赖则留空数组，不得成环，无依赖子任务不要伪造依赖；"
    "priority 是整数、取值**越大越先执行**（同波次就绪队列内降序调度），没有偏好时留 0；"
    'difficulty 是该子任务的难易度，只能取 "easy" / "medium" / "hard" 三档之一，'
    "把握不足时取 medium；目标本身不可再分时，只输出 1 个子任务。"
)

_VERIFY_SYSTEM = (
    "你是验收判定器。对照验收标准判定子任务结果是否达标，"
    '仅输出 JSON：{"passed": true, "reason": "..."}。'
    "只依据给出的事实判定，不要替结果补全任何未出现的信息；"
    "结果未提供、与标准无关、信息被截断而缺少关键证据、或未达标准时判 false，"
    "并给出一句话理由（不要复述结果全文）。"
)

_MAX_VERIFY_CHARS = 4000  # 验收判定输入截断（结果正文有界）
_MAX_SUCCESS_CRITERIA = 5  # 任务级成功标准条数上界（prompt 约定 2-5 条）
_MAX_OUTCOME_REPLY = 500  # 任务级判定里每个子任务结果节选上界


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

    async def __call__(self, goal: str) -> DecomposeResult:
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
        parsed = self._parse(response.content)
        return parsed if parsed.subtasks else self._fallback(goal)

    def _parse(self, content: str) -> DecomposeResult:
        """逐项校验模型输出（id/goal 非空、depends_on 引用已声明 id），非法项剔除。"""
        data = _extract_json(content)
        criteria: list[str] = []
        if isinstance(data, dict):
            table = cast(dict[str, Any], data)
            criteria = self._parse_criteria(table.get("success_criteria"))
            data = table.get("subtasks")
        if not isinstance(data, list):
            return DecomposeResult(subtasks=[], success_criteria=criteria)
        entries = cast(list[Any], data)
        items = [cast(dict[str, Any], item) for item in entries if isinstance(item, dict)]
        ids = {
            str(item.get("id", "")).strip()
            for item in items
            if str(item.get("id", "")).strip() and str(item.get("goal", "")).strip()
        }
        subtasks: list[Subtask] = []
        seen: set[str] = set()
        for item in items:
            sid = str(item.get("id", "")).strip()
            sgoal = str(item.get("goal", "")).strip()
            if not sid or not sgoal or sid in seen:
                continue  # 重复 id 保留首个（重复会使拓扑序不完整、被误报成环）
            seen.add(sid)
            raw_deps = item.get("depends_on")
            depends_on = (
                [
                    dep
                    for dep in (str(dep).strip() for dep in cast(list[Any], raw_deps))
                    if dep in ids
                ]
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
        return DecomposeResult(subtasks=subtasks, success_criteria=criteria)

    @staticmethod
    def _parse_criteria(raw: Any) -> list[str]:
        """成功标准解析：仅保留非空字符串、strip、保序去重、至多 5 条。"""
        if not isinstance(raw, list):
            return []
        criteria: list[str] = []
        for item in cast(list[Any], raw):
            text = item.strip() if isinstance(item, str) else ""
            if text and text not in criteria:
                criteria.append(text)
                if len(criteria) >= _MAX_SUCCESS_CRITERIA:
                    break
        return criteria

    @staticmethod
    def _fallback(goal: str) -> DecomposeResult:
        """回落单子任务（不带标准）：目标整体交执行循环（多轮工具调用仍可推进）。

        planner 调用失败时若仍生成标准，同源 LLM 判定失败会把本可执行的任务拖死
        ⇒ 回落路径的标准恒为空（change 0248）。
        """
        return DecomposeResult(subtasks=[Subtask(id="1", goal=goal, acceptance="")])


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
        verdict = await _judge(self._llm, request)
        if verdict is None:
            verdict = await _judge(self._llm, request)
        return verdict if verdict is not None else _fail_closed()


async def _judge(llm: LLMProvider, request: LLMRequest) -> VerifyResult | None:
    """单次判定：可解析返回判定；调用失败/不可解析返回 None（可重试）。"""
    try:
        response = await llm.acompletion(request)
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


def _fail_closed() -> VerifyResult:
    return VerifyResult(passed=False, reason="验收判定失败（fail-closed）: 输出不可解析或调用失败")


class LLMTaskVerifier:
    """LLM 任务级判定器：对照整体成功标准与子任务结果判定任务是否达成。

    复用 ``_VERIFY_SYSTEM`` 判定协议与单次重试 / fail-closed 口径（不新增 prompt 常量）。
    输入中的子任务结果摘要有界且经 ``redact_secrets`` 脱敏（密钥形态子串不进提示词）。
    """

    def __init__(self, llm: LLMProvider, *, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def __call__(
        self, goal: str, criteria: list[str], outcomes: list[SubtaskOutcome]
    ) -> VerifyResult:
        if not criteria:  # 空标准短路（调度器通常已先行跳过）
            return VerifyResult(passed=True, reason="无任务级成功标准")
        request = LLMRequest(
            messages=[
                Message(role="system", content=_VERIFY_SYSTEM),
                Message(role="user", content=self._render(goal, criteria, outcomes)),
            ],
            model=self._model or "",
        )
        verdict = await _judge(self._llm, request)
        if verdict is None:
            verdict = await _judge(self._llm, request)
        return verdict if verdict is not None else _fail_closed()

    @staticmethod
    def _render(goal: str, criteria: list[str], outcomes: list[SubtaskOutcome]) -> str:
        """渲染判定输入：目标 + 标准逐条 + 结果摘要；整体脱敏并有界。"""
        lines = [f"任务目标：{goal}", "成功标准："]
        lines.extend(f"- {criterion}" for criterion in criteria)
        lines.append("子任务结果：")
        for outcome in outcomes:
            state = "通过" if outcome.ok else f"失败（{outcome.reason}）"
            lines.append(f"- {outcome.subtask_id}：{state}")
            if outcome.reply:
                lines.append(f"  结果：{outcome.reply[:_MAX_OUTCOME_REPLY]}")
        return redact_secrets("\n".join(lines))[:_MAX_VERIFY_CHARS]
