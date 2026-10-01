"""JEVProvider（JEV/TypeSafe System One 决策小模型接入）。

经 TypeSafe 专有 REST 端点（POST /v1/systemone）挂接 JEV：以 stdlib
``urllib.request`` 发 HTTP（零新三方依赖，契合「核心零第三方运行时依赖」
红线），Bearer 认证；提交 state + typed questions，返回 typed answers
（map<id, Answer>，按原语分形）。答案与问题 schema 不匹配抛
``JUDGMENT_SCHEMA_MISMATCH``；端点不可达抛 ``JUDGMENT_PROVIDER_UNREACHABLE``；
超时抛 ``JUDGMENT_TIMEOUT``（后两者由 DecisionRouter 捕获转为回退）。

对应接口：doc/03-interfaces/judgment-interface.md §3
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, cast

from .errors import JudgmentError, JudgmentErrorCode

# 各原语答案的必需字段（按原语分形校验）。
_REQUIRED_ANSWER_KEYS: dict[str, set[str]] = {
    "choice": {"choice", "probabilities", "confidence"},
    "score": {"score", "legend", "probabilities", "confidence"},
    "noul": {"noul", "probability"},
}


class JEVProvider:
    """经 TypeSafe REST 端点挂接 JEV System One。"""

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def query(
        self, state: str | dict[str, Any] | list[Any], questions: dict[str, Any]
    ) -> dict[str, Any]:
        """提交 state + typed questions，返回 typed answers（map<id, Answer>）。"""
        payload = {"state": state, "model": self._model, "questions": questions}
        request = urllib.request.Request(
            f"{self._base_url}/v1/systemone",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise JudgmentError(
                JudgmentErrorCode.JUDGMENT_TIMEOUT, f"JEV 决策超时: {self._base_url}"
            ) from exc
        except OSError as exc:
            raise JudgmentError(
                JudgmentErrorCode.JUDGMENT_PROVIDER_UNREACHABLE,
                f"JEV 端点不可达: {self._base_url}",
            ) from exc
        raw_answers = body.get("answers", {})
        if not isinstance(raw_answers, dict):
            raise JudgmentError(
                JudgmentErrorCode.JUDGMENT_SCHEMA_MISMATCH, "JEV 响应缺 answers 映射"
            )
        answers = cast(dict[str, Any], raw_answers)
        self._validate(answers, questions)
        return answers

    def _validate(self, answers: dict[str, Any], questions: dict[str, Any]) -> None:
        """校验 typed answers 与 questions 的 schema 一致（原语 + 必需字段）。"""
        for question_id, answer in answers.items():
            question = questions.get(question_id)
            if not isinstance(question, dict):
                raise JudgmentError(
                    JudgmentErrorCode.JUDGMENT_SCHEMA_MISMATCH, f"答案 {question_id} 无对应问题"
                )
            primitive = str(cast(dict[str, Any], question).get("primitive", ""))
            required = _REQUIRED_ANSWER_KEYS.get(primitive)
            if required is None or not isinstance(answer, dict):
                raise JudgmentError(
                    JudgmentErrorCode.JUDGMENT_SCHEMA_MISMATCH,
                    f"答案 {question_id} 原语未知或非对象: {primitive}",
                )
            missing = required - answer.keys()
            if missing:
                raise JudgmentError(
                    JudgmentErrorCode.JUDGMENT_SCHEMA_MISMATCH,
                    f"答案 {question_id} 缺字段: {sorted(missing)}",
                )
