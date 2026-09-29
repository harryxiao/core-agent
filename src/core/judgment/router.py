"""决策路由（DecisionRouter）。

统一决策入口：按原语分发到 JEV，低置信度 / 端点不可达 / 超时自动回退主 LLM
兜底；每次决策产出 ``DecisionTrace`` 落 observability 供进化/审批消费。

对应接口：doc/03-interfaces/judgment-interface.md §2
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any, cast

from core.llm_provider import LLMError, LLMProvider, LLMRequest, Message
from core.observability import TraceEvent, Tracer

from .errors import JudgmentError, JudgmentErrorCode
from .models import DecisionPrimitive, DecisionRequest, DecisionResult, DecisionTrace
from .provider import JEVProvider

# noul 概率接近 0.5 的判定窗口：是/否概率各半视为无信息量，触发回退。
_NOUL_AMBIGUOUS_EPS = 0.05


class DecisionRouter:
    """choice/decide 决策原语路由：统一决策入口 + 置信度回退主 LLM。"""

    def __init__(
        self,
        *,
        provider: JEVProvider | None = None,
        fallback: LLMProvider | None = None,
        confidence_threshold: float = 0.7,
        tracer: Tracer | None = None,
    ) -> None:
        self._provider = provider
        self._fallback = fallback
        self._confidence_threshold = confidence_threshold
        self._tracer = tracer

    def choose(
        self, state: dict[str, Any], options: list[str], threshold: float | None = None
    ) -> DecisionResult:
        """以 choice 原语从候选中路由出唯一分支，选中项及置信度见 result.answers。"""
        request = DecisionRequest(
            primitive=DecisionPrimitive.CHOICE,
            state=state,
            questions={"choice": {"primitive": "choice", "options": options}},
            options=options,
            threshold=threshold,
        )
        return self.decide(request)

    def decide(self, request: DecisionRequest) -> DecisionResult:
        """统一决策入口：按原语分发到 JEV，低置信度自动回退主 LLM。"""
        if not isinstance(cast(Any, request.primitive), DecisionPrimitive):
            raise JudgmentError(
                JudgmentErrorCode.JUDGMENT_INVALID_PRIMITIVE,
                f"未识别决策原语: {request.primitive}",
            )
        if self._provider is None:
            return self._fallback_result(request, JudgmentErrorCode.JUDGMENT_PROVIDER_UNREACHABLE)
        try:
            answers = self._provider.query(request.state, request.questions)
        except JudgmentError as exc:
            if exc.code in (
                JudgmentErrorCode.JUDGMENT_PROVIDER_UNREACHABLE,
                JudgmentErrorCode.JUDGMENT_TIMEOUT,
            ):
                return self._fallback_result(request, exc.code)
            raise
        if self._low_confidence(request.primitive, answers, request.threshold):
            return self._fallback_result(request, JudgmentErrorCode.JUDGMENT_LOW_CONFIDENCE)
        result = DecisionResult(primitive=request.primitive, answers=answers, fallback=False)
        self._record(request, result)
        return result

    def _low_confidence(
        self, primitive: DecisionPrimitive, answers: dict[str, Any], threshold: float | None
    ) -> bool:
        """choice/score 以 confidence 判定；noul 以概率接近 0.5 判定。"""
        t = threshold if threshold is not None else self._confidence_threshold
        if primitive is DecisionPrimitive.NOUL:
            for answer in answers.values():
                if not isinstance(answer, dict):
                    continue
                probability = cast(dict[str, Any], answer).get("probability")
                ambiguous = (
                    isinstance(probability, (int, float))
                    and abs(probability - 0.5) < _NOUL_AMBIGUOUS_EPS
                )
                if ambiguous:
                    return True
            return False
        confidences: list[float] = []
        for answer in answers.values():
            if not isinstance(answer, dict):
                continue
            confidence = cast(dict[str, Any], answer).get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
        return bool(confidences) and min(confidences) < t

    def _fallback_result(
        self, request: DecisionRequest, reason: JudgmentErrorCode
    ) -> DecisionResult:
        """回退主 LLM 兜底，产出按原语分形的答案（map<question_id, Answer>）。"""
        content = self._run_fallback_llm(request)
        answer = self._fallback_answer(request.primitive, request.options, content)
        question_id = next(iter(request.questions), request.primitive.value)
        result = DecisionResult(
            primitive=request.primitive, answers={question_id: answer}, fallback=True
        )
        self._record(request, result, reason)
        return result

    def _run_fallback_llm(self, request: DecisionRequest) -> str:
        """经主 LLM 兜底；未注入 fallback 时返回空串（能力完全关闭）。"""
        if self._fallback is None:
            return ""
        llm_request = LLMRequest(
            messages=[Message(role="user", content=self._fallback_prompt(request))],
            model="fallback",  # 占位：真实模型由宿主注入的主 LLM 配置决定
        )
        try:
            response = self._fallback.completion(llm_request)
        except LLMError:
            return ""
        return response.content

    def _fallback_prompt(self, request: DecisionRequest) -> str:
        """组装回退 prompt：state + 原语说明 + 候选选项。"""
        state = request.state if isinstance(request.state, str) else repr(request.state)
        prompt = f"决策原语: {request.primitive.value}\n上下文: {state}"
        if request.options:
            prompt += "\n候选选项: " + ", ".join(request.options)
        return prompt

    def _fallback_answer(
        self, primitive: DecisionPrimitive, options: list[str] | None, content: str
    ) -> dict[str, Any]:
        """把主 LLM 文本塑形为按原语分形的答案。"""
        text = (content or "").strip()
        if primitive is DecisionPrimitive.CHOICE:
            return {
                "choice": self._pick_option(text, options or []),
                "probabilities": {},
                "confidence": 0.0,
            }
        if primitive is DecisionPrimitive.SCORE:
            return {"score": 0.0, "legend": text, "probabilities": {}, "confidence": 0.0}
        return {"noul": self._parse_yes(text), "probability": 0.5}

    def _pick_option(self, text: str, options: list[str]) -> str:
        """从候选选项中挑出主 LLM 文本命中的首个选项，兜底取首项。"""
        lowered = text.lower()
        for option in options:
            if option.lower() in lowered:
                return option
        return options[0] if options else ""

    def _parse_yes(self, text: str) -> bool:
        """从主 LLM 文本解析是/否结论。"""
        lowered = text.lower()
        return any(token in lowered for token in ("yes", "true", "是", "放行"))

    def _record(
        self,
        request: DecisionRequest,
        result: DecisionResult,
        reason: JudgmentErrorCode | None = None,
    ) -> None:
        """每次决策产出 DecisionTrace 落 observability（含置信度 + 回退标记）。"""
        if self._tracer is None:
            return
        trace = DecisionTrace(
            trace_id=uuid.uuid4().hex, request=request, result=result, ts=time.time()
        )
        payload = asdict(trace)
        if reason is not None:
            payload["fallback_reason"] = reason.value
        self._tracer.record(
            TraceEvent(
                trace_id=trace.trace_id,
                span_id=uuid.uuid4().hex,
                ts=trace.ts,
                kind="decision",
                payload=payload,
            )
        )
