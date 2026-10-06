"""验证门（evolution）。

review + 运行时测试 → `GateReport.passed`；任一不过则阻断发布（spec「验证门」）。

**两个判据的生产者都由组合根注入**（本模块此前是「恒通过桩」的缺省值 ⇒ 门恒开、「未过门丢弃」
生产不可达）：
- **review**：`build_review_prompt` 渲染候选**自身是否自洽**的判据面（kind / 目标 / 变更内容），
  模型调用由组合根给（`review_with`）—— 照 ``author.py`` 先例、ADR-0045 同一依赖方向：
  evolution **不 import 任何 LLM 抽象**，prompt 文本属本域。
- **运行时测试**：结晶面门禁（`ci_cd.crystallization_gates()` **按标记派生**自门禁命令单一真源
  `GATE_COMMANDS`）经**独立执行面**（子进程）真实执行，执行器同样由组合根注入。

判据一律 **fail-closed**：未注入生产者 / review 输出不可解析 / 调用失败 / 门禁跑不起来
⇒ **未通过**。`test_results` 的值恒为 `bool` —— `validate` 用 ``all(...)`` 汇总结论，
值里混进失败原因**字符串**会被当成真值（失败读成通过）。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「验证门」
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from .models import GateReport, GenerationCandidate


class GateOutcome(Protocol):
    """门禁结果的最小结构契约（消费侧只读 `passed`；不 import ci-cd 类型，依赖方向不变）。"""

    passed: bool


#: prompt → 文本的模型调用（由组合根注入）
LlmText = Callable[[str], str]
#: review 生产者：候选 ⇒ 是否通过
Review = Callable[[GenerationCandidate], bool]
#: 运行时测试生产者：候选 ⇒ 门名 → 是否通过（值恒 `bool`）
GateTests = Callable[[GenerationCandidate], dict[str, bool]]
#: 门禁执行面：门名 ⇒ 门禁结果
RunGate = Callable[[str], GateOutcome]

_REVIEW_PROMPT_HEAD = (
    "你是候选变更的审查者。只审这一个候选**自身是否自洽**（候选类型 / 目标模块 / 变更内容三者"
    "是否互相说得通、是否是真该由该目标承担的变更）；不评收益、不写实现。"
    "第一行以 PASS 起首表示通过，以 REJECT 起首表示不通过，其后可附一句理由。"
)

#: 判定词表：**首行**以「通过词」起首才算通过；其余（明确的 REJECT / 空 / 含糊 / 调用失败）
#: 一律不通过。
_PASS_WORDS = ("PASS", "通过")


def build_review_prompt(candidate: GenerationCandidate) -> str:
    """把候选的自洽性判据面渲染为审查 prompt。"""
    return "\n".join(
        [
            _REVIEW_PROMPT_HEAD,
            "",
            f"候选类型：{candidate.kind}",
            f"目标模块：{candidate.target_plugin}",
            f"变更内容：{candidate.delta}",
        ]
    )


def parse_review(text: str) -> bool:
    """解析审查判定：只认**首行**以通过词起首；词表外一律不通过（fail-closed）。"""
    lines = text.strip().splitlines()
    if not lines:
        return False
    return lines[0].strip().upper().startswith(_PASS_WORDS)


def review_with(llm: LlmText) -> Review:
    """把「prompt → 文本」的模型调用适配为审查者契约（前例 ``author.patch_author_with``）。"""

    def _review(candidate: GenerationCandidate) -> bool:
        try:
            return parse_review(llm(build_review_prompt(candidate)))
        except Exception:  # noqa: BLE001 — 模型不可用 ⇒ 无判据 ⇒ 不得放行（fail-closed）
            return False

    return _review


def run_gate_tests(*, run_gate: RunGate, gates: Sequence[str]) -> GateTests:
    """把「门名 ⇒ 门禁结果」的执行面适配为运行时测试契约（只跑传入的标记子集）。"""

    def _tests(_candidate: GenerationCandidate) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for kind in gates:
            try:
                results[kind] = bool(run_gate(kind).passed)
            except Exception:  # noqa: BLE001 — 跑不起来（工具缺失/执行面故障）⇒ 该门未通过
                results[kind] = False
        return results

    return _tests


class Validator:
    """验证门：review 判定 + 运行时测试结果共同决定 passed（判据缺一不得放行）。"""

    plugin_id = "evolution.validator"

    def __init__(
        self,
        *,
        review: Review | None = None,
        tests: GateTests | None = None,
    ) -> None:
        self._review = review
        self._tests = tests

    def validate(self, candidate: GenerationCandidate) -> GateReport:
        review, tests = self._review, self._tests
        if review is None or tests is None:
            # 无判据不得当通过（缺省 `Validator()` 恒通过正是本 Requirement 要消除的形态）。
            producers = (("review", review), ("运行时测试", tests))
            missing = "、".join(name for name, producer in producers if producer is None)
            return GateReport(
                passed=False, review=f"{missing}生产者未注入：无法判定", test_results={}
            )
        if not review(candidate):
            # fail-fast：门已未过，不做无谓的子进程开销（也不据空结果伪装成「测过」）。
            return GateReport(passed=False, review="拒绝", test_results={})
        test_results = tests(candidate)
        # `bool(test_results)`：空测试集不得当通过（`all({})` 为真）。
        passed = bool(test_results) and all(test_results.values())
        return GateReport(passed=passed, review="通过", test_results=test_results)
