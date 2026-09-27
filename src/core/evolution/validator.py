"""验证门（evolution）。

review + 运行时测试 → `GateReport.passed`；任一不过则阻断发布。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「验证门」
"""

from __future__ import annotations

from collections.abc import Callable

from .models import GateReport, GenerationCandidate


def _review_pass(_candidate: GenerationCandidate) -> bool:
    return True


def _no_tests(_candidate: GenerationCandidate) -> dict[str, bool]:
    return {}


class Validator:
    """验证门：review 判定 + 运行时测试结果共同决定 passed。"""

    plugin_id = "evolution.validator"

    def __init__(
        self,
        *,
        review: Callable[[GenerationCandidate], bool] | None = None,
        tests: Callable[[GenerationCandidate], dict[str, bool]] | None = None,
    ) -> None:
        self._review = review if review is not None else _review_pass
        self._tests = tests if tests is not None else _no_tests

    def validate(self, candidate: GenerationCandidate) -> GateReport:
        review_ok = self._review(candidate)
        test_results = self._tests(candidate)
        passed = review_ok and all(test_results.values())
        review_text = "通过" if review_ok else "拒绝"
        return GateReport(passed=passed, review=review_text, test_results=test_results)
