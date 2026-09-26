"""constraints 单元测试（对齐规格场景 + §7 专属校验锚点）。

覆盖：输入校验拒绝、输出解析失败、熔断开合与短路、指数退避封顶、
失败回滚触发 EffectTracker、上下文压缩去重。
"""

from __future__ import annotations

import pytest

from core.constraints import (
    CircuitBreaker,
    ConstraintError,
    ConstraintErrorCode,
    ContextCompressor,
    ExecContext,
    ExecRequest,
    RetryPolicy,
    Rollback,
    Validator,
)
from core.plugin_registry import Effect, EffectTracker

_MAX_BACKOFF = 8.0  # RetryPolicy.backoff 封顶值（对齐 fault_tolerance 内部 8.0）

_SCHEMA = {
    "type": "object",
    "properties": {"count": {"type": "integer"}},
    "required": ["count"],
}


def _ctx(trace_id: str = "t") -> ExecContext:
    return ExecContext(trace_id=trace_id)


def _req() -> ExecRequest:
    return ExecRequest(tool="t", args={}, schema={}, trace_id="t")


# ---- 输入校验 ----


def test_validate_input_rejects() -> None:
    validator = Validator()
    assert validator.validate_input("t", {}, _SCHEMA) != []  # 缺少必填
    assert validator.validate_input("t", {"count": "x"}, _SCHEMA) != []  # 类型不符


def test_validate_input_passes() -> None:
    validator = Validator()
    assert validator.validate_input("t", {"count": 1}, _SCHEMA) == []


# ---- 输出解析 ----


def test_parse_output_failure() -> None:
    validator = Validator()
    with pytest.raises(ConstraintError) as exc_info:
        validator.parse_output("not-json", _SCHEMA)
    assert exc_info.value.code is ConstraintErrorCode.OUTPUT_PARSE_FAILED


def test_parse_output_success() -> None:
    validator = Validator()
    parsed = validator.parse_output('{"action": "read"}', _SCHEMA)
    assert parsed.ok is True
    assert parsed.instruction == {"action": "read"}


# ---- 熔断 ----


def test_circuit_breaker_open_and_short_circuit() -> None:
    cb = CircuitBreaker(failure_threshold=2, cooldown_s=30.0)
    cb.record_result(False)
    cb.record_result(False)
    assert cb.state == "OPEN"
    with pytest.raises(ConstraintError) as exc_info:
        cb.before(_ctx(), _req())
    assert exc_info.value.code is ConstraintErrorCode.CIRCUIT_OPEN
    with pytest.raises(ConstraintError):
        cb.before(_ctx(), _req())  # 短路期内持续快速失败，核心不执行


def test_circuit_breaker_half_open_recovers() -> None:
    cb = CircuitBreaker(failure_threshold=2, cooldown_s=0.0)
    cb.record_result(False)
    cb.record_result(False)
    assert cb.state == "HALF_OPEN"  # 冷却期满，半开试探
    cb.record_result(True)
    assert cb.state == "CLOSED"  # 试探成功，重新闭合


# ---- 重试 ----


def test_retry_backoff_exponential() -> None:
    policy = RetryPolicy(base_delay=0.5, jitter=0.0)
    assert policy.backoff(1) < policy.backoff(2) < policy.backoff(3)
    assert policy.backoff(10) == _MAX_BACKOFF  # 指数退避封顶


def test_retry_should_retry() -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(1, TimeoutError()) is True  # 可重试错误未超限
    assert policy.should_retry(3, TimeoutError()) is False  # 达到上限
    structural = ConstraintError(ConstraintErrorCode.CIRCUIT_OPEN, "open")
    assert policy.should_retry(1, structural) is False  # 结构性错误不重试


# ---- 回滚 ----


def test_rollback_on_failure() -> None:
    tracker = EffectTracker()
    undone: list[str] = []
    tracker.record(
        Effect(
            op="write",
            target="f.txt",
            undo=lambda: undone.append("f.txt"),
            reversible=True,
            coeffect=["filesystem:write"],
            trace_id="t1",
            ts=0.0,
        )
    )
    rollback = Rollback(tracker)
    resp = rollback.on_failure(_ctx("t1"), _req(), RuntimeError("boom"))
    assert resp.ok is False
    assert undone == ["f.txt"]


# ---- 上下文压缩 ----


def test_compress_dedup_and_keep() -> None:
    compressor = ContextCompressor()
    messages = [
        {"role": "system", "content": "关键约束"},
        {"role": "user", "content": "待办事项"},
        {"role": "assistant", "content": "子任务A [已完成]"},
        {"role": "user", "content": "待办事项"},
        {"role": "assistant", "content": "[done] 子任务B"},
    ]
    assert compressor.compress(messages) == [
        {"role": "system", "content": "关键约束"},
        {"role": "user", "content": "待办事项"},
    ]
