"""结晶面门的判定面：真实 review + 真实运行时测试（change 0120 / phase-31 切片 2）。

phase-31 G1 + G2：生产装配的 `Validator()` 无参 ⇒ `_review_pass` 恒真、`_no_tests` 返 `{}`
（`all({})` 为真）⇒ 验证门恒通过、`rejected` 分支**生产不可达**（G5）。本文件证明四件事：
① 结晶面门禁子集**按标记从 `GATE_COMMANDS` 派生**（不另立清单、标记漂移即失败）；
② review 由**注入的审查者**产出且判定 **fail-closed**（不可解析 / 调用失败 ⇒ 未通过）；
③ 运行时测试由**注入的执行面**真实跑标记门禁，任一门未过 ⇒ 门未过；
④ **未注入生产者 ⇒ 不得放行**，且生产装配下 `run_cycle` 真的走真 review + 真门禁（G5 锚点：
`rejected` 生产可达）。
"""

from __future__ import annotations

from typing import Any

import pytest

from core.ci_cd import (
    CRYSTALLIZATION_GATE_MARKS,
    GATE_COMMANDS,
    CiCdError,
    crystallization_gates,
)
from core.configuration import ConfigManager
from core.evolution import (
    GATE_CALIBER,
    Diagnoser,
    DiagnosisReport,
    Evaluator,
    EvolutionEngine,
    GenerationCandidate,
    Proposer,
    Trace,
    Validator,
)
from core.evolution.validator import (
    build_review_prompt,
    parse_review,
    review_with,
    run_gate_tests,
)
from core.runtime import build_runtime

# ---- 夹具 ----


def _candidate(plugin_id: str = "memory.retrieve") -> GenerationCandidate:
    return Proposer().propose(DiagnosisReport(target_plugin=plugin_id, issue="检索失败"))


def _trace(trace_id: str = "1", *, plugin_id: str = "memory.retrieve") -> Trace:
    """一条**失败且带结果**的 trace（缺结果者被采集器视作无证据，不进诊断）。"""
    return Trace(
        trace_id=trace_id,
        task_type="t",
        action={"a": 1},
        result="err",
        success=False,
        plugin_id=plugin_id,
    )


class _GateOutcome:
    """门禁结果替身（结构上等价 ci-cd 的 `GateResult`：消费侧只要求 `passed`）。"""

    def __init__(self, passed: bool) -> None:
        self.passed = passed


def _engine(validator: Validator, *, evaluator: Evaluator | None = None) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=validator,
        evaluator=evaluator if evaluator is not None else Evaluator(),
    )


# ---- 1. 结晶面门禁子集：按标记从单一真源派生 ----


def test_crystallization_gates_derived_from_single_source() -> None:
    """子集 = `lint` + `test`，顺序随单一真源；命中的门名都真在 `GATE_COMMANDS` 里。"""
    gates = crystallization_gates()
    assert gates == ("lint", "test")
    assert all(kind in GATE_COMMANDS for kind in gates)
    # 顺序随真源（而非标记的书写顺序）：真源顺序即结晶面执行顺序
    marked = set(gates)
    assert gates == tuple(kind for kind in GATE_COMMANDS if kind in marked)
    # 命令字符串仍**只有一份**（在 GATE_COMMANDS 里）
    assert GATE_COMMANDS["lint"] == "ruff check src tests"
    assert GATE_COMMANDS["test"] == "pytest -q"


def test_crystallization_gates_exclude_delivery_face_gates() -> None:
    """类型卫生（typecheck）与打包（build）不进结晶面（spec 明文：与「能否发布」无因果）。"""
    gates = crystallization_gates()
    assert "typecheck" not in gates
    assert "build" not in gates
    assert set(gates) | {"typecheck", "build"} == set(GATE_COMMANDS)


def test_crystallization_marks_unknown_gate_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """标记命中真源里**不存在**的门名 ⇒ 派生失败（不得静默少跑一门）。"""
    monkeypatch.setattr(
        "core.ci_cd.pipeline.CRYSTALLIZATION_GATE_MARKS",
        {"lint": "x", "test": "y", "不存在的门": "z"},
    )
    with pytest.raises(CiCdError):
        crystallization_gates()


def test_crystallization_marks_carry_names_not_commands() -> None:
    """标记只标**门名**（值是可读理由），不复制门禁命令（不另立第二份清单）。"""
    assert set(CRYSTALLIZATION_GATE_MARKS) <= set(GATE_COMMANDS)
    commands = set(GATE_COMMANDS.values())
    assert not commands.intersection(CRYSTALLIZATION_GATE_MARKS.values())


# ---- 2. review 的生产者：结构化审查 + fail-closed 判定 ----


def test_review_prompt_carries_candidate_facts() -> None:
    """prompt 带上候选的自洽性判据面（kind / 目标 / delta）—— 审的是候选自身，不是收益。"""
    candidate = _candidate()
    prompt = build_review_prompt(candidate)
    assert candidate.target_plugin in prompt
    assert candidate.kind in prompt
    assert candidate.delta["issue"] in prompt
    assert "PASS" in prompt  # 判定词表写进 prompt（模型知道要输出什么）


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PASS", True),
        ("PASS\n理由：kind 与目标自洽", True),
        ("pass", True),
        ("通过", True),
        ("\n\nPASS", True),
        ("REJECT: delta 与目标不自洽", False),
        ("拒绝：目标不存在", False),
        ("也许吧", False),
        ("", False),
        ("   \n  ", False),
        # 等值判定反证：前缀匹配会把下面三条读成通过（fail-open）
        ("通过不了，delta 与目标不自洽", False),
        ("PASS 但存在问题", False),
        ("PASSING", False),
    ],
)
def test_parse_review_fail_closed(text: str, expected: bool) -> None:
    """判定词表外（含空 / 含糊 / 以通过词起首的否定句）一律**不通过**（fail-closed）。"""
    assert parse_review(text) is expected


def test_review_with_llm_passes() -> None:
    """审查者输出 PASS ⇒ review 通过。"""
    assert review_with(lambda _prompt: "PASS")(_candidate()) is True


def test_review_with_llm_garbage_denies() -> None:
    """审查者输出不可解析 ⇒ 不通过（不得以「看不懂」当通过）。"""
    assert review_with(lambda _prompt: "嗯，还行吧")(_candidate()) is False


def test_review_with_llm_failure_denies() -> None:
    """审查者不可用（调用抛异常）⇒ 不通过（fail-closed，不外抛）。"""

    def _boom(_prompt: str) -> str:
        raise RuntimeError("端点不可达")

    assert review_with(_boom)(_candidate()) is False


# ---- 3. 运行时测试的生产者：真跑标记门禁 ----


def test_run_gate_tests_runs_only_marked_gates() -> None:
    """只跑传入的标记子集，结果按门名收集（值恒为布尔）。"""
    called: list[str] = []

    def _run_gate(kind: str) -> _GateOutcome:
        called.append(kind)
        return _GateOutcome(passed=True)

    tests = run_gate_tests(run_gate=_run_gate, gates=crystallization_gates())
    results = tests(_candidate())
    assert called == ["lint", "test"]
    assert results == {"lint": True, "test": True}
    assert all(isinstance(value, bool) for value in results.values())


def test_run_gate_tests_marks_failed_gate() -> None:
    """某道门未过 ⇒ 据实为 `False`（值恒布尔 —— 塞原因字符串会被 `all()` 看成真）。"""
    tests = run_gate_tests(
        run_gate=lambda kind: _GateOutcome(passed=kind == "lint"), gates=("lint", "test")
    )
    assert tests(_candidate()) == {"lint": True, "test": False}


def test_run_gate_tests_runner_exception_fails_closed() -> None:
    """门禁「跑不起来」（执行面抛异常）⇒ 该门未通过，不外抛（与交付面同口径）。"""

    def _boom(_kind: str) -> _GateOutcome:
        raise OSError("找不到可执行文件")

    tests = run_gate_tests(run_gate=_boom, gates=("lint", "test"))
    assert tests(_candidate()) == {"lint": False, "test": False}


# ---- 4. Validator：无判据不得放行 + 两个判据都要过 ----


def test_default_validator_denies() -> None:
    """缺省 `Validator()`（未注入任何生产者）⇒ 未通过，理由据实写明「未注入」。"""
    report = Validator().validate(_candidate())
    assert report.passed is False
    assert "未注入" in report.review
    assert report.test_results == {}


def test_validator_denies_when_only_one_producer_injected() -> None:
    """只注入一半判据 ⇒ 仍不得放行（无判据不得当通过）。"""
    assert Validator(review=lambda _c: True).validate(_candidate()).passed is False
    assert Validator(tests=lambda _c: {"unit": True}).validate(_candidate()).passed is False


def test_validator_passes_when_both_judgments_pass() -> None:
    """两个判据都过 ⇒ 通过（review 文本「通过」）。"""
    validator = Validator(review=lambda _c: True, tests=lambda _c: {"unit": True})
    report = validator.validate(_candidate())
    assert report.passed is True
    assert report.review == "通过"
    assert report.test_results == {"unit": True}


def test_validator_denies_when_review_rejects() -> None:
    """review 未过 ⇒ 门未过；且**不**白跑子进程门禁（fail-fast：门已未过）。"""
    calls: list[str] = []
    validator = Validator(
        review=lambda _c: False, tests=lambda _c: (calls.append("ran"), {"unit": True})[1]
    )
    report = validator.validate(_candidate())
    assert report.passed is False
    assert report.review == "拒绝"
    assert calls == []


def test_validator_denies_when_a_gate_fails() -> None:
    """任一门禁未过 ⇒ 门未过。"""
    validator = Validator(review=lambda _c: True, tests=lambda _c: {"lint": True, "test": False})
    report = validator.validate(_candidate())
    assert report.passed is False
    assert report.test_results == {"lint": True, "test": False}


def test_validator_denies_on_empty_test_set() -> None:
    """空测试集**不得**当作通过（`all({})` 为真正是 G2 的成因）。"""
    validator = Validator(review=lambda _c: True, tests=lambda _c: {})
    assert validator.validate(_candidate()).passed is False


# ---- 5. 端到端：未过门 ⇒ `rejected`（G5 锚点） ----


def test_run_cycle_reports_rejected_on_failed_gate() -> None:
    """G5 锚点：判定面装真判据后，「未过门 ⇒ rejected」在**闭环**上可发生（不再恒 pending）。"""
    validator = Validator(
        review=review_with(lambda _prompt: "REJECT: delta 与目标不自洽"),
        tests=run_gate_tests(
            run_gate=lambda kind: _GateOutcome(passed=kind == "lint"),
            gates=crystallization_gates(),
        ),
    )
    outcome = _engine(validator).run_cycle([_trace()])
    assert outcome.status == "rejected"
    assert outcome.gate is not None and outcome.gate.passed is False


def test_run_cycle_reaches_eval_when_gate_passes() -> None:
    """门过了才进留出评测（判据顺序不变）：无基准 ⇒ 评审判 `frozen`（不是 `rejected`）。"""
    validator = Validator(
        review=lambda _c: True,
        tests=run_gate_tests(
            run_gate=lambda _kind: _GateOutcome(passed=True), gates=crystallization_gates()
        ),
    )
    outcome = _engine(validator).run_cycle([_trace()])
    assert outcome.status == "frozen"


# ---- 6. 组合根装配：生产形状真的走真 review + 真门禁子集 ----


def _write_llm_config(tmp_path: Any) -> ConfigManager:
    """写一份最小 LLM 配置并返回其配置管理器（端点指向不可达的示例域，模型面一律打桩）。"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    return ConfigManager(yaml_path=str(cfg))


class _Reply:
    """模型回复替身（只要求 `.content`）。"""

    def __init__(self, content: str) -> None:
        self.content = content


#: change 0236：技能内容蒸馏 prompt 命中时返回合法 JSON（与审查 PASS 分流）
_SKILL_CONTENT_JSON = (
    '{"task_types":["t"],"instructions":"步骤","param_schema":{},'
    '"preconditions":[],"description":""}'
)


def _stub_llm_provider(content: str, *, boom: bool = False) -> Any:
    """模型提供者替身：`content` 是审查者输出；`boom` 模拟端点不可达。

    技能内容蒸馏（change 0236）与审查共用 `_llm_text`：蒸馏 prompt 返回合法 JSON，
    其余 prompt 返回 ``content``（审查词）。
    """

    class _Provider:
        def __init__(self, **_kwargs: Any) -> None: ...

        def completion(self, request: Any) -> _Reply:
            if boom:
                raise RuntimeError("端点不可达")
            prompt = request.messages[0].content
            if "技能内容蒸馏器" in prompt:
                return _Reply(_SKILL_CONTENT_JSON)
            return _Reply(content)

    return _Provider


def _stub_gate_executor(calls: list[str], *, passed: bool = True) -> Any:
    """门禁执行器工厂替身：记录被跑的门名（装配面不桩，桩的是子进程与模型两个外部面）。"""

    class _Result:
        reason = ""

        def __init__(self) -> None:
            self.passed = passed

    def _factory(**_kwargs: Any) -> Any:
        def _run(gate: Any) -> _Result:
            calls.append(gate.kind)
            return _Result()

        return _run

    return _factory


def test_runtime_runs_real_review_and_marked_gates(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生产装配：`run_cycle` 走**真 review**（组合根接缝）+ **真门禁子集**（标记派生那两道）。"""
    gate_calls: list[str] = []
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _stub_llm_provider("PASS"))
    monkeypatch.setattr("core.runtime.build_gate_executor", _stub_gate_executor(gate_calls))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(_write_llm_config(tmp_path))
    assert runtime.evolution is not None
    outcome = runtime.evolution.engine.run_cycle([_trace()])
    # 真 review 通过 ⇒ 走到真门禁（跑的是标记派生的两道）⇒ 全过 ⇒ 进留出评测 ⇒ 无基准 ⇒ frozen
    assert gate_calls == ["lint", "test"]
    assert outcome.status == "frozen"


def test_runtime_denies_when_review_unavailable(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生产装配：模型端点不可用 ⇒ review 判**未通过** ⇒ 门未过 ⇒ `rejected`（不谎报为其它结局）。"""
    gate_calls: list[str] = []
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _stub_llm_provider("", boom=True))
    monkeypatch.setattr("core.runtime.build_gate_executor", _stub_gate_executor(gate_calls))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(_write_llm_config(tmp_path))
    assert runtime.evolution is not None
    outcome = runtime.evolution.engine.run_cycle([_trace()])
    assert outcome.status == "rejected"
    assert gate_calls == []  # review 未过 ⇒ 运行时测试根本不必跑（fail-fast）


# ---- 7. 口径版本：判定面变了 ⇒ 必须递增 ----

#: 判定面真实化（change 0120 / ADR-0113）所定的口径版本**下限**：后续任何判定口径变更只会更高。
_JUDGMENT_FACE_CALIBER = 2


def test_gate_caliber_bumped_for_judgment_face() -> None:
    """判定口径变更（本次换掉两个恒通过桩）⇒ `GATE_CALIBER` 已递增（旧口径候选不得投放）。"""
    assert GATE_CALIBER >= _JUDGMENT_FACE_CALIBER
