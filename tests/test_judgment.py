"""judgment 单元测试（对齐 spec/judgment + judgment-interface.md + M8 验收）。

覆盖：
- 三原语分发（choice / score / noul）按原语分形
- JEV 协议适配（state + typed questions → typed answers）+ schema 校验
- 置信度回退（confidence < 阈值 / noul 概率 ≈0.5 / 不可达 / 超时）
- 未识别原语 → JUDGMENT_INVALID_PRIMITIVE
- 决策轨迹落 observability（含置信度 + 回退标记）
- 未配置 provider → 决策能力关闭、回退主 LLM 兜底
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.judgment import (
    Compactor,
    DecisionPrimitive,
    DecisionRequest,
    DecisionRouter,
    Guardrail,
    JEVProvider,
    JudgmentError,
    JudgmentErrorCode,
    SkillMatcher,
    SopGate,
)


class _FakeProvider:
    """Duck-typed JEVProvider 替身：可配置答案或抛出 JudgmentError。"""

    def __init__(
        self,
        answers: dict[str, Any] | None = None,
        error: JudgmentError | None = None,
    ) -> None:
        self._answers = answers or {}
        self._error = error
        self.queries: list[tuple[Any, dict[str, Any]]] = []

    def query(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        self.queries.append((state, questions))
        if self._error is not None:
            raise self._error
        return self._answers


class _FakeFallback:
    """Duck-typed LLMProvider 替身：记录调用并返回固定文本。"""

    def __init__(self, content: str = "") -> None:
        self._content = content
        self.calls = 0

    def completion(self, request: Any) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(content=self._content)


class _FakeTracer:
    """Duck-typed Tracer 替身：捕获 decision 事件。"""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def record(self, event: Any) -> None:
        self.events.append(event)


# ---- 三原语分发 ----


def test_choice_returns_unique_pick_with_confidence() -> None:
    answers = {"choice": {"choice": "b", "probabilities": {"a": 0.1, "b": 0.9}, "confidence": 0.95}}
    router = DecisionRouter(provider=_FakeProvider(answers=answers), fallback=_FakeFallback())
    result = router.choose({"ctx": "x"}, ["a", "b"])
    assert result.primitive is DecisionPrimitive.CHOICE
    assert result.fallback is False
    assert result.answers["choice"]["choice"] == "b"
    assert result.answers["choice"]["confidence"] == 0.95  # noqa: PLR2004


def test_score_returns_scores() -> None:
    answers = {"score": {"score": 0.8, "legend": "high", "probabilities": {}, "confidence": 0.9}}
    compactor = Compactor(
        DecisionRouter(provider=_FakeProvider(answers=answers), fallback=_FakeFallback())
    )
    result = compactor.score({"ctx": "x"}, [{"id": "i1"}])
    assert result.primitive is DecisionPrimitive.SCORE
    assert result.fallback is False
    assert result.answers["score"]["score"] == 0.8  # noqa: PLR2004


def test_noul_returns_boolean() -> None:
    answers = {"noul": {"noul": True, "probability": 0.95}}
    guardrail = Guardrail(
        DecisionRouter(provider=_FakeProvider(answers=answers), fallback=_FakeFallback())
    )
    result = guardrail.check({"ctx": "x"}, {"op": "file.write"})
    assert result.primitive is DecisionPrimitive.NOUL
    assert result.fallback is False
    assert result.answers["noul"]["noul"] is True


# ---- 置信度回退 ----


def test_low_confidence_falls_back_to_main_llm() -> None:
    answers = {"choice": {"choice": "b", "probabilities": {}, "confidence": 0.3}}
    fallback = _FakeFallback(content="a")
    router = DecisionRouter(provider=_FakeProvider(answers=answers), fallback=fallback)
    result = router.choose({"ctx": "x"}, ["a", "b"], threshold=0.7)
    assert result.fallback is True
    assert fallback.calls == 1
    assert result.answers["choice"]["choice"] == "a"  # 命中 fallback 文本


def test_noul_ambiguous_probability_falls_back() -> None:
    answers = {"noul": {"noul": True, "probability": 0.5}}
    fallback = _FakeFallback(content="no")
    guardrail = Guardrail(
        DecisionRouter(provider=_FakeProvider(answers=answers), fallback=fallback)
    )
    result = guardrail.check({"ctx": "x"}, {"op": "file.write"})
    assert result.fallback is True
    assert fallback.calls == 1
    assert result.answers["noul"]["noul"] is False


def test_unreachable_falls_back() -> None:
    error = JudgmentError(JudgmentErrorCode.JUDGMENT_PROVIDER_UNREACHABLE, "down")
    fallback = _FakeFallback(content="a")
    router = DecisionRouter(provider=_FakeProvider(error=error), fallback=fallback)
    result = router.choose({"ctx": "x"}, ["a", "b"])
    assert result.fallback is True
    assert fallback.calls == 1


def test_timeout_falls_back() -> None:
    error = JudgmentError(JudgmentErrorCode.JUDGMENT_TIMEOUT, "slow")
    fallback = _FakeFallback(content="a")
    router = DecisionRouter(provider=_FakeProvider(error=error), fallback=fallback)
    result = router.choose({"ctx": "x"}, ["a", "b"])
    assert result.fallback is True
    assert fallback.calls == 1


def test_schema_mismatch_propagates() -> None:
    error = JudgmentError(JudgmentErrorCode.JUDGMENT_SCHEMA_MISMATCH, "bad")
    router = DecisionRouter(provider=_FakeProvider(error=error), fallback=_FakeFallback())
    with pytest.raises(JudgmentError) as exc_info:
        router.choose({"ctx": "x"}, ["a", "b"])
    assert exc_info.value.code == JudgmentErrorCode.JUDGMENT_SCHEMA_MISMATCH


def test_invalid_primitive_raises() -> None:
    router = DecisionRouter(provider=_FakeProvider(), fallback=_FakeFallback())
    request = DecisionRequest(primitive="bogus", state={}, questions={})  # type: ignore[arg-type]
    with pytest.raises(JudgmentError) as exc_info:
        router.decide(request)
    assert exc_info.value.code == JudgmentErrorCode.JUDGMENT_INVALID_PRIMITIVE


# ---- 未配置 provider 决策能力关闭 ----


def test_unconfigured_provider_falls_back() -> None:
    fallback = _FakeFallback(content="a")
    router = DecisionRouter(provider=None, fallback=fallback)
    result = router.choose({"ctx": "x"}, ["a", "b"])
    assert result.fallback is True
    assert fallback.calls == 1


def test_fully_unconfigured_returns_best_effort() -> None:
    router = DecisionRouter(provider=None, fallback=None)
    result = router.choose({"ctx": "x"}, ["a", "b"])
    assert result.fallback is True
    assert result.answers["choice"]["choice"] == "a"  # 兜底取首项
    assert result.answers["choice"]["confidence"] == 0.0


# ---- 决策轨迹落 observability ----


def test_decision_trace_emitted() -> None:
    answers = {"choice": {"choice": "b", "probabilities": {}, "confidence": 0.9}}
    tracer = _FakeTracer()
    router = DecisionRouter(
        provider=_FakeProvider(answers=answers), fallback=_FakeFallback(), tracer=tracer
    )
    router.choose({"ctx": "x"}, ["a", "b"])
    assert len(tracer.events) == 1
    event = tracer.events[0]
    assert event.kind == "decision"
    payload = event.payload
    assert payload["trace_id"]
    assert isinstance(payload["ts"], float)
    assert payload["result"]["fallback"] is False
    assert payload["result"]["answers"]["choice"]["choice"] == "b"


def test_fallback_trace_marks_reason() -> None:
    error = JudgmentError(JudgmentErrorCode.JUDGMENT_TIMEOUT, "slow")
    tracer = _FakeTracer()
    router = DecisionRouter(
        provider=_FakeProvider(error=error), fallback=_FakeFallback(content="a"), tracer=tracer
    )
    router.choose({"ctx": "x"}, ["a", "b"])
    event = tracer.events[0]
    assert event.payload["result"]["fallback"] is True
    assert event.payload["fallback_reason"] == "JUDGMENT_TIMEOUT"


# ---- JEV 协议适配（真实 urllib 经 mock urlopen） ----


def test_jev_provider_query_adapts_protocol() -> None:
    provider = JEVProvider(api_key="secret-token", base_url="http://jev.local", model="systemone")
    body = json.dumps(
        {"answers": {"choice": {"choice": "a", "probabilities": {"a": 0.9}, "confidence": 0.9}}}
    ).encode("utf-8")
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = body
    with patch("core.judgment.provider.urllib.request.urlopen", return_value=response) as urlopen:
        answers = provider.query({"ctx": "x"}, {"choice": {"primitive": "choice"}})
    assert answers["choice"]["choice"] == "a"
    req = urlopen.call_args[0][0]
    assert req.full_url == "http://jev.local/v1/systemone"
    sent = json.loads(req.data.decode("utf-8"))
    assert sent["state"] == {"ctx": "x"}
    assert sent["model"] == "systemone"
    assert sent["questions"] == {"choice": {"primitive": "choice"}}
    assert req.get_header("Authorization") == "Bearer secret-token"


def test_jev_provider_schema_mismatch() -> None:
    provider = JEVProvider(api_key="k", base_url="http://jev.local", model="m")
    # 缺 probabilities/confidence 字段
    body = json.dumps({"answers": {"choice": {"choice": "a"}}}).encode("utf-8")
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = body
    with (
        patch("core.judgment.provider.urllib.request.urlopen", return_value=response),
        pytest.raises(JudgmentError) as exc_info,
    ):
        provider.query({}, {"choice": {"primitive": "choice"}})
    assert exc_info.value.code == JudgmentErrorCode.JUDGMENT_SCHEMA_MISMATCH


def test_jev_provider_unreachable() -> None:
    provider = JEVProvider(api_key="k", base_url="http://jev.local", model="m")
    with (
        patch("core.judgment.provider.urllib.request.urlopen", side_effect=OSError("refused")),
        pytest.raises(JudgmentError) as exc_info,
    ):
        provider.query({}, {"choice": {"primitive": "choice"}})
    assert exc_info.value.code == JudgmentErrorCode.JUDGMENT_PROVIDER_UNREACHABLE


def test_jev_provider_timeout() -> None:
    provider = JEVProvider(api_key="k", base_url="http://jev.local", model="m")
    with (
        patch("core.judgment.provider.urllib.request.urlopen", side_effect=TimeoutError()),
        pytest.raises(JudgmentError) as exc_info,
    ):
        provider.query({}, {"choice": {"primitive": "choice"}})
    assert exc_info.value.code == JudgmentErrorCode.JUDGMENT_TIMEOUT


# ---- 技能语义匹配（SkillMatcher，0044） ----


def _scored_provider(
    scores: dict[str, float], *, error: JudgmentError | None = None
) -> _FakeProvider:
    """按候选逐条作答的打分器替身：skill_id 无分 → 返回坏答案（缺 score 键）。"""

    class _Provider(_FakeProvider):
        def query(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
            self.queries.append((state, questions))
            if error is not None:
                raise error
            skill_id = questions["score"]["items"][0]["skill_id"]
            if skill_id not in scores:
                return {"score": {"legend": "?", "probabilities": {}, "confidence": 0.5}}
            return {
                "score": {
                    "score": scores[skill_id],
                    "legend": "match",
                    "probabilities": {},
                    "confidence": 0.9,
                }
            }

    return _Provider()


def _candidates(*skill_ids: str) -> list[dict[str, Any]]:
    return [{"skill_id": sid, "description": sid, "task_types": [sid]} for sid in skill_ids]


def test_skill_matcher_scores_each_candidate_once() -> None:
    provider = _scored_provider({"a": 0.9, "b": 0.3})
    matcher = SkillMatcher(DecisionRouter(provider=provider, fallback=_FakeFallback()))
    expected = {"a": 0.9, "b": 0.3}  # noqa: PLR2004
    assert matcher.score("整理会议纪要", _candidates("a", "b")) == expected
    # score 原语只给「条目集单一分数」→ 逐候选一次调用，每次只送一条候选
    assert len(provider.queries) == 2  # noqa: PLR2004
    assert all(len(q[1]["score"]["items"]) == 1 for q in provider.queries)


def test_skill_matcher_skips_bad_answer() -> None:
    provider = _scored_provider({"a": 0.9})
    matcher = SkillMatcher(DecisionRouter(provider=provider, fallback=_FakeFallback()))
    assert matcher.score("任务", _candidates("a", "b")) == {"a": 0.9}  # noqa: PLR2004


def test_skill_matcher_returns_empty_on_provider_failure() -> None:
    provider = _scored_provider(
        {}, error=JudgmentError(JudgmentErrorCode.JUDGMENT_PROVIDER_UNREACHABLE, "boom")
    )
    matcher = SkillMatcher(DecisionRouter(provider=provider, fallback=_FakeFallback()))
    # 回退答案给 SCORE 的分恒为 0.0 → 不产生伪命中
    assert matcher.score("任务", _candidates("a")) == {}


def test_skill_matcher_without_candidates_makes_no_call() -> None:
    provider = _scored_provider({"a": 0.9})
    matcher = SkillMatcher(DecisionRouter(provider=provider, fallback=_FakeFallback()))
    assert matcher.score("任务", []) == {}
    assert provider.queries == []


# ---- SOP 自动质量门（SopGate，0198 / ADR-0188） ----


def _noul_gate(answer: dict[str, Any]) -> tuple[SopGate, _FakeProvider]:
    """真 `DecisionRouter` + 预设 noul 答案的门（不触网）。"""
    provider = _FakeProvider(answers=answer)
    return SopGate(DecisionRouter(provider=provider, fallback=_FakeFallback())), provider


class _RaisingRouter:
    """判定路由替身：`decide` 直接抛（模拟路由层外故障）。"""

    def decide(self, request: Any) -> Any:
        raise RuntimeError("路由不可用")  # noqa: TRY003


class _ShapelessRouter:
    """判定路由替身：返回**结构不符**的结果（answers 缺 `noul` 键）。"""

    def decide(self, request: Any) -> Any:
        return SimpleNamespace(answers={"noul": {"probability": 0.5}})


def test_sop_gate_maps_noul_answer() -> None:
    gate, provider = _noul_gate({"noul": {"noul": True, "probability": 0.95}})

    assert gate("整理会议纪要", "1. 读输入\n2. 输出摘要") is True, "noul=True ⇒ 放行"

    state, questions = provider.queries[0]
    assert state == {"task": "整理会议纪要"}, "判定上下文携带任务文本"
    action = questions["noul"]["action"]
    assert action["kind"] == "publish_sop" and "读输入" in action["sop"], "门看得到提炼正文"


def test_sop_gate_rejects_when_noul_false() -> None:
    gate, _ = _noul_gate({"noul": {"noul": False, "probability": 0.95}})
    assert gate("任务", "空泛步骤") is False


def test_sop_gate_fails_open_on_judgment_fault() -> None:
    """判定**故障**（路由抛异常）⇒ 放行（fail-open：不阻断发布）。"""
    gate = SopGate(_RaisingRouter())  # type: ignore[arg-type] — 替身契约：只用到 decide
    assert gate("任务", "步骤") is True


def test_sop_gate_fails_open_on_missing_answer() -> None:
    """答案**结构不符**（缺 `noul` 键）⇒ 放行（fail-open）。"""
    gate = SopGate(_ShapelessRouter())  # type: ignore[arg-type]
    assert gate("任务", "步骤") is True
