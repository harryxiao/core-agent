"""tool-use 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：schema 非法注册拒绝、参数校验、coeffect 缺失、确认门（只读/可逆写
auto、不可逆写/高风险 confirm、显式拒绝 deny）、效应记录与回滚、声明/行为
不符告警、超时、异步真并发，以及 secret/external coeffect 不成为验收盲区。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from core.plugin_registry import CoeffectResolver, SecretRef
from core.tools import (
    GateDecision,
    SafetyGate,
    Tool,
    ToolDef,
    ToolErrorCode,
    ToolProvider,
    ToolUseError,
    file_read,
    file_write,
)

_DELAY = 0.1
_SERIAL_THRESHOLD = 0.18  # 串行两次 sleep ≈ 2*_DELAY，真并发应显著低于此值

_ECHO_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    return ToolProvider(coeffect_resolver=resolver)


def _echo_tool() -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="test.echo",
            description="echo",
            schema=_ECHO_SCHEMA,
            coeffects=["filesystem:read"],
            reversible=False,
        ),
        handler=lambda text: text,
    )


async def _slow(text: str) -> str:
    await asyncio.sleep(0.2)
    return text


async def _sleep_then(text: str) -> str:
    await asyncio.sleep(_DELAY)
    return text


class _DenyGate:
    def confirm(
        self, tool_id: str, args: dict, coeffects: list[str], reversible: bool
    ) -> GateDecision:
        return GateDecision("deny", "test deny")


# ---- 注册期 schema 非法拒绝 ----


def test_register_invalid_schema_rejected() -> None:
    provider = ToolProvider()
    bad = Tool(
        definition=ToolDef(
            tool_id="test.bad",
            description="",
            schema="not-a-dict",
            coeffects=[],
            reversible=False,
        ),
        handler=lambda: None,
    )
    with pytest.raises(ToolUseError) as exc_info:
        provider.register(bad)
    assert exc_info.value.code is ToolErrorCode.INVALID_TOOL_SCHEMA


# ---- 参数校验 ----


def test_invoke_missing_arg() -> None:
    provider = _provider()
    provider.register(_echo_tool())
    result = provider.invoke("test.echo", {}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.INVALID_ARGS


def test_invoke_unknown_tool() -> None:
    provider = _provider()
    result = provider.invoke("test.nope", {}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.INVALID_ARGS


# ---- 只读自动执行 ----


def test_readonly_auto_execute() -> None:
    provider = _provider()
    provider.register(_echo_tool())
    result = provider.invoke("test.echo", {"text": "hi"}, trace_id="t")
    assert result.ok is True
    assert result.data == "hi"
    assert result.effect_id is None  # 只读无效应


# ---- coeffect 缺失 ----


def test_coeffect_missing() -> None:
    provider = ToolProvider()  # 空 resolver
    provider.register(_echo_tool())
    result = provider.invoke("test.echo", {"text": "hi"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.COEFFECT_MISSING


# ---- 确认门 ----


def test_gate_readonly_and_reversible_auto() -> None:
    gate = SafetyGate()
    assert gate.confirm("t", {}, ["filesystem:read"], False).action == "auto"
    assert gate.confirm("t", {}, ["filesystem:write"], True).action == "auto"


def test_gate_irreversible_and_high_risk_confirm() -> None:
    gate = SafetyGate()
    assert gate.confirm("t", {}, ["filesystem:write"], False).action == "confirm"
    assert gate.confirm("t", {}, ["secret:api_key"], True).action == "confirm"
    assert gate.confirm("t", {}, ["external"], True).action == "confirm"
    assert gate.confirm("t", {}, ["network:outbound"], True).action == "confirm"


def test_irreversible_write_blocked() -> None:
    provider = _provider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="test.irrev",
                description="",
                schema=_ECHO_SCHEMA,
                coeffects=["filesystem:write"],
                reversible=False,
            ),
            handler=lambda text: text,
        )
    )
    result = provider.invoke("test.irrev", {"text": "x"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.IRREVERSIBLE_BLOCKED


def test_gate_denied() -> None:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    provider = ToolProvider(coeffect_resolver=resolver, gate=_DenyGate())
    provider.register(_echo_tool())
    result = provider.invoke("test.echo", {"text": "hi"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.GATE_DENIED


# ---- secret/external coeffect 不盲区 ----


def test_secret_coeffect_handle_not_leaked() -> None:
    resolver = CoeffectResolver()
    resolver.register("secret:api_key", "sk-RAW-SECRET", secret=True)
    ctx = resolver.resolve(["secret:api_key"])
    handle = ctx.get("secret:api_key")
    assert isinstance(handle, SecretRef)
    assert handle.name == "secret:api_key"
    assert "sk-RAW-SECRET" not in repr(handle)  # 密钥值绝不落 repr


def test_secret_coeffect_blocked_by_gate() -> None:
    resolver = CoeffectResolver()
    resolver.register("secret:api_key", "sk-raw", secret=True)
    provider = ToolProvider(coeffect_resolver=resolver)
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="test.secret",
                description="",
                schema=_ECHO_SCHEMA,
                coeffects=["secret:api_key"],
                reversible=False,
            ),
            handler=lambda text: text,
        )
    )
    result = provider.invoke("test.secret", {"text": "x"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.IRREVERSIBLE_BLOCKED


# ---- 声明/行为不符告警 ----


def test_undeclared_write_warning() -> None:
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="test.warn",
                description="",
                schema=_ECHO_SCHEMA,
                coeffects=["filesystem:read"],  # 声明读
                reversible=True,
            ),
            handler=lambda text: text,
            undo=lambda: None,  # 却携带撤销闭包
        )
    )
    assert provider.warnings != []


# ---- 可逆写 + 回滚 ----


def test_reversible_write_rollback(tmp_path) -> None:
    path = tmp_path / "f.txt"
    path.write_text("original")
    provider = _provider()
    provider.register(file_write())
    result = provider.invoke(
        "tools.file_write", {"path": str(path), "content": "changed"}, trace_id="t1"
    )
    assert result.ok is True
    assert result.effect_id is not None
    assert path.read_text() == "changed"
    report = provider.rollback("t1")
    assert result.effect_id in report.reverted
    assert path.read_text() == "original"


def test_file_read_builtin(tmp_path) -> None:
    path = tmp_path / "r.txt"
    path.write_text("line1\nline2")
    provider = _provider()
    provider.register(file_read())
    result = provider.invoke("tools.file_read", {"path": str(path)}, trace_id="t")
    assert result.ok is True
    assert result.data["content"] == "line1\nline2"


# ---- 超时 ----


def test_timeout() -> None:
    provider = _provider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="test.slow",
                description="",
                schema=_ECHO_SCHEMA,
                coeffects=[],
                reversible=False,
                timeout_s=0.05,
            ),
            handler=_slow,
        )
    )
    result = provider.invoke("test.slow", {"text": "x"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.TIMEOUT


# ---- ainvoke ≡ invoke + 真并发 ----


def test_invoke_ainvoke_equivalent() -> None:
    provider = _provider()
    provider.register(_echo_tool())
    sync = provider.invoke("test.echo", {"text": "hi"}, trace_id="t")
    async_res = asyncio.run(provider.ainvoke("test.echo", {"text": "hi"}, trace_id="t"))
    assert sync.ok == async_res.ok
    assert sync.data == async_res.data == "hi"


def test_async_true_concurrency() -> None:
    async def main() -> tuple[bool, bool, float]:
        provider = _provider()
        provider.register(
            Tool(
                definition=ToolDef(
                    tool_id="test.slow",
                    description="",
                    schema=_ECHO_SCHEMA,
                    coeffects=[],
                    reversible=False,
                    timeout_s=1.0,
                ),
                handler=_sleep_then,
            )
        )
        start = time.perf_counter()
        r1, r2 = await asyncio.gather(
            provider.ainvoke("test.slow", {"text": "a"}, trace_id="t1"),
            provider.ainvoke("test.slow", {"text": "b"}, trace_id="t2"),
        )
        return r1.ok, r2.ok, time.perf_counter() - start

    ok1, ok2, elapsed = asyncio.run(main())
    assert ok1 and ok2
    assert elapsed < _SERIAL_THRESHOLD
