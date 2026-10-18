"""tool-use 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：schema 非法注册拒绝、参数校验、coeffect 缺失、确认门（只读/可逆写
auto、不可逆写/高风险 confirm、显式拒绝 deny）、效应记录与回滚、声明/行为
不符告警、超时、异步真并发，以及 secret/external coeffect 不成为验收盲区。
"""

from __future__ import annotations

import asyncio
import os
import stat
import time
from unittest.mock import patch

import pytest

import core.tools.provider as provider_module
from core.constraints import Validator
from core.plugin_registry import CoeffectResolver, SecretRef
from core.tools import (
    GateDecision,
    SafetyGate,
    Tool,
    ToolDef,
    ToolErrorCode,
    ToolProvider,
    ToolUseError,
    code_run,
    file_patch,
    file_read,
    file_write,
    web_fetch,
)
from core.tools.builtin import _MAX_FETCH_BYTES, _MAX_OUTPUT_CHARS  # noqa: PLC2701 — 截断上界断言
from core.tools.env_shell import EnvironmentSnapshot

_DELAY = 0.1
_HTTP_OK = 200  # FakeHTTPResponse 默认状态码
_SERIAL_THRESHOLD = 0.18  # 串行两次 sleep ≈ 2*_DELAY，真并发应显著低于此值
_MODE_640 = 0o640  # 权限位保留断言用的既有文件模式

_ECHO_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    resolver.register("process:spawn", True)
    resolver.register("network:outbound", True)
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


def test_invoke_handler_exception_structured() -> None:
    """handler 执行异常归一 EXECUTION_FAILED（不向调用方抛裸异常，主循环可继续）。"""
    provider = _provider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="test.boom",
                description="必炸",
                schema=_ECHO_SCHEMA,
                coeffects=["filesystem:read"],
                reversible=False,
            ),
            handler=lambda text: (_ for _ in ()).throw(ValueError("bad mode")),
        )
    )
    result = provider.invoke("test.boom", {"text": "hi"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ToolErrorCode.EXECUTION_FAILED
    assert "执行失败" in result.error.message


def test_file_write_normalizes_mode_alias(tmp_path) -> None:
    """模型语义 mode（write/append）归一为 Python open 模式。"""
    target = tmp_path / "a.txt"
    provider = _provider()
    provider.register(file_write())
    first = provider.invoke(
        "tools.file_write",
        {"path": str(target), "content": "x", "mode": "write"},
        trace_id="t",
    )
    second = provider.invoke(
        "tools.file_write",
        {"path": str(target), "content": "y", "mode": "append"},
        trace_id="t",
    )
    assert first.ok and second.ok
    assert target.read_text(encoding="utf-8") == "xy"


# ---- 覆盖写入原子性（change 0257 / ADR-0248） ----


def test_file_write_overwrite_is_atomic_without_temp_residue(tmp_path) -> None:
    """覆盖写入 ⇒ 目标为新内容，目录中不残留临时文件。"""
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    provider = _provider()
    provider.register(file_write())

    result = provider.invoke(
        "tools.file_write", {"path": str(target), "content": "new"}, trace_id="t"
    )

    assert result.ok
    assert target.read_text(encoding="utf-8") == "new"
    assert [entry.name for entry in tmp_path.iterdir()] == ["a.txt"]


def test_file_write_replace_failure_leaves_target_unchanged(tmp_path) -> None:
    """替换阶段失败 ⇒ 目标逐字保持原内容，临时文件被清理。"""
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    provider = _provider()
    provider.register(file_write())

    with patch("core.tools.builtin.os.replace", side_effect=OSError("replace boom")):
        result = provider.invoke(
            "tools.file_write",
            {"path": str(target), "content": "new"},
            trace_id="t",
        )

    assert result.ok is False
    assert target.read_text(encoding="utf-8") == "old"
    assert [entry.name for entry in tmp_path.iterdir()] == ["a.txt"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX 权限位")
def test_file_write_overwrite_preserves_permission_bits(tmp_path) -> None:
    """替换既有文件 ⇒ 保留其权限位（临时文件的 0o666 不覆盖目标模式）。"""
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    os.chmod(target, _MODE_640)
    provider = _provider()
    provider.register(file_write())

    result = provider.invoke(
        "tools.file_write", {"path": str(target), "content": "new"}, trace_id="t"
    )

    assert result.ok
    assert stat.S_IMODE(target.stat().st_mode) == _MODE_640


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
            undo=lambda: lambda: None,  # 却携带撤销闭包（工厂形态）
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


# ---- 同一工具多次写入：按次快照（change 0129 / E64） ----


def test_same_tool_keeps_per_call_snapshots(tmp_path) -> None:
    """同一 file_write 写 A 再写 B ⇒ 逆序回滚**逐次各归各位**（不恢复错文件）。"""
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("A0")
    provider = _provider()
    provider.register(file_write())
    provider.invoke("tools.file_write", {"path": str(a), "content": "A1"}, trace_id="t")
    provider.invoke("tools.file_write", {"path": str(b), "content": "B1"}, trace_id="t")
    assert a.read_text() == "A1" and b.read_text() == "B1"

    provider.rollback("t")

    assert a.read_text() == "A0", "第 1 次写入前的原内容"
    assert not b.exists(), "B 原本不存在 ⇒ 撤销即删除"


def test_interleaved_write_and_patch_restore_in_lifo_order(tmp_path) -> None:
    """write → patch → write 交错 ⇒ 逆序逐次还原（write 的共享快照曾被最后一次覆写）。"""
    path = tmp_path / "f.txt"
    path.write_text("one two three")
    provider = _provider()
    provider.register(file_write())
    provider.register(file_patch())
    provider.invoke("tools.file_write", {"path": str(path), "content": "alpha"}, trace_id="t")
    provider.invoke(
        "tools.file_patch",
        {"path": str(path), "old_content": "alpha", "new_content": "beta"},
        trace_id="t",
    )
    provider.invoke("tools.file_write", {"path": str(path), "content": "gamma"}, trace_id="t")
    assert path.read_text() == "gamma"

    provider.rollback("t")

    assert path.read_text() == "one two three"


def test_snapshots_do_not_leak_across_traces(tmp_path) -> None:
    """只回滚 t1 ⇒ t2 的写入**逐字不变**（快照不跨 trace 串用）。"""
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("A0")
    b.write_text("B0")
    provider = _provider()
    provider.register(file_write())
    provider.invoke("tools.file_write", {"path": str(a), "content": "A1"}, trace_id="t1")
    provider.invoke("tools.file_write", {"path": str(b), "content": "B1"}, trace_id="t2")

    provider.rollback("t1")

    assert a.read_text() == "A0", "t1 的写入被还原"
    assert b.read_text() == "B1", "t2 的写入不被 t1 的回滚触及"


def test_undo_without_prior_write_is_noop(tmp_path) -> None:
    """空栈取撤销闭包 ⇒ no-op（不抛异常、不动文件系统）。"""
    path = tmp_path / "f.txt"
    path.write_text("original")
    tool = file_write()
    assert tool.undo is not None
    undo = tool.undo()
    undo()  # 未写入即撤销：静默 no-op
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


# ---- code_run / web_fetch 内置原子工具 ----


class _FakeProc:
    """异步子进程替身（change 0259 执行 seam）。"""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = 999999  # 不存在的 pid：kill 分支走 ProcessLookupError 兜底

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        pass


def test_code_run_python_and_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    """code_run 执行 python/bash 片段，返回码与 stdout 正确映射。"""
    provider = _provider()
    provider.register(code_run())
    py = provider.invoke(
        "tools.code_run", {"script": "print(21 * 2)", "type": "python"}, trace_id="t", approved=True
    )
    assert py.ok and py.data["returncode"] == 0 and py.data["stdout"].strip() == "42"

    # bash：注入「有 bash」快照 + 替身 exec（宿主未必装 Git Bash，change 0237 fail-closed）
    async def fake_exec(*cmd: object, **_kw: object) -> _FakeProc:
        assert cmd[:2] == ("bash", "-c")
        return _FakeProc(stdout=b"bash-ok\n")

    monkeypatch.setattr("core.tools.execution._create_subprocess_exec", fake_exec)
    snap = EnvironmentSnapshot(
        os="Linux",
        default_shell="bash",
        shell_label="bash",
        path_style="posix",
        has_pwsh=False,
        has_powershell=False,
        has_bash=True,
    )
    provider2 = _provider()
    provider2.register(code_run(env_snapshot=snap))
    sh = provider2.invoke(
        "tools.code_run", {"script": "echo bash-ok", "type": "bash"}, trace_id="t", approved=True
    )
    assert sh.ok and sh.data["stdout"].strip() == "bash-ok"


def test_code_run_timeout_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    """脚本超时：进程树被终止并归一 TIMEOUT，不向调用方抛裸异常。"""

    class _HangingProc(_FakeProc):
        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(5)
            return b"", b""

    async def fake_exec(*_a: object, **_kw: object) -> _HangingProc:
        return _HangingProc()

    monkeypatch.setattr("core.tools.execution._create_subprocess_exec", fake_exec)
    snap = EnvironmentSnapshot(
        os="Linux",
        default_shell="bash",
        shell_label="bash",
        path_style="posix",
        has_pwsh=False,
        has_powershell=False,
        has_bash=True,
    )
    provider = _provider()
    provider.register(code_run(env_snapshot=snap))
    result = provider.invoke(
        "tools.code_run",
        {"script": "sleep 1", "type": "bash", "timeout": 0.05},
        trace_id="t",
        approved=True,
    )
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.TIMEOUT


def test_code_run_long_output_keeps_head_and_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    """超限输出首尾保留：总长仍 ≤ 上限，标记可见，截断标志不变。"""
    long_stdout = "HEAD-" + "a" * 5000 + "b" * 5000 + "-TAIL"

    async def fake_exec(*_a: object, **_kw: object) -> _FakeProc:
        return _FakeProc(stdout=long_stdout.encode("utf-8"))

    monkeypatch.setattr("core.tools.execution._create_subprocess_exec", fake_exec)
    provider = _provider()
    provider.register(code_run())
    result = provider.invoke(
        "tools.code_run", {"script": "print(1)", "type": "python"}, trace_id="t", approved=True
    )

    assert result.ok
    stdout = result.data["stdout"]
    assert result.data["stdout_truncated"] is True
    assert len(stdout) <= _MAX_OUTPUT_CHARS
    assert stdout.startswith("HEAD-")
    assert stdout.endswith("-TAIL")
    assert "[truncated" in stdout


def test_code_run_short_output_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_exec(*_a: object, **_kw: object) -> _FakeProc:
        return _FakeProc(stdout=b"short output\n")

    monkeypatch.setattr("core.tools.execution._create_subprocess_exec", fake_exec)
    provider = _provider()
    provider.register(code_run())
    result = provider.invoke(
        "tools.code_run", {"script": "print(1)", "type": "python"}, trace_id="t", approved=True
    )

    assert result.ok
    assert result.data["stdout"] == "short output\n"
    assert result.data["stdout_truncated"] is False


def test_code_run_blocked_without_approval() -> None:
    """code_run 不可逆高风险：无批准（approved/approver 均无）即 fail-closed。"""
    provider = _provider()
    provider.register(code_run())
    result = provider.invoke("tools.code_run", {"script": "print(1)"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.IRREVERSIBLE_BLOCKED


class _FakeHTTPResponse:
    """urlopen 返回的上下文管理器形状（status/headers/read）。"""

    def __init__(self, body: bytes, status: int = 200, content_type: str = "text/html") -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = body

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_web_fetch_maps_response() -> None:
    provider = _provider()
    provider.register(web_fetch())
    with patch(
        "core.tools.builtin.urllib.request.urlopen",
        return_value=_FakeHTTPResponse(b"<html>hello</html>"),
    ) as mocked:
        result = provider.invoke(
            "tools.web_fetch", {"url": "https://example.com"}, trace_id="t", approved=True
        )
    assert result.ok
    assert result.data["status"] == _HTTP_OK
    assert result.data["body"] == "<html>hello</html>"
    assert result.data["truncated"] is False
    assert mocked.call_args is not None  # 真发起了出站 GET


def test_web_fetch_truncates_body() -> None:
    """正文按字节上限截断并置 truncated 标记。"""
    provider = _provider()
    provider.register(web_fetch())
    with patch(
        "core.tools.builtin.urllib.request.urlopen",
        return_value=_FakeHTTPResponse(b"x" * (_MAX_FETCH_BYTES + 10)),
    ):
        result = provider.invoke(
            "tools.web_fetch", {"url": "https://example.com"}, trace_id="t", approved=True
        )
    assert result.ok
    assert len(result.data["body"]) == _MAX_FETCH_BYTES
    assert result.data["truncated"] is True


def test_web_fetch_rejects_non_http() -> None:
    """仅接受 http/https：file:// 等协议经结构化错误拒绝（SSRF 防线）。"""
    provider = _provider()
    provider.register(web_fetch())
    result = provider.invoke(
        "tools.web_fetch", {"url": "file:///etc/passwd"}, trace_id="t", approved=True
    )
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.EXECUTION_FAILED
    assert "http" in result.error.message


# ---- 确认门审批通道 ----


def _approving_provider(approver) -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("network:outbound", True)
    return ToolProvider(coeffect_resolver=resolver, approver=approver)


def test_confirm_gate_approval_decides_execution() -> None:
    """确认门 confirm：经审批通道决断——批准放行、拒绝 fail-closed。"""
    asked: list[str] = []

    async def approver(tool_id, args, reason):  # noqa: ANN001 — 测试内鸭子类型
        asked.append(tool_id)
        return args.get("url") == "https://a.example"

    provider = _approving_provider(approver)
    provider.register(web_fetch())
    with patch("core.tools.builtin.urllib.request.urlopen", return_value=_FakeHTTPResponse(b"ok")):
        ok = provider.invoke("tools.web_fetch", {"url": "https://a.example"}, trace_id="t")
    denied = provider.invoke("tools.web_fetch", {"url": "https://b.example"}, trace_id="t")
    assert ok.ok and ok.data["body"] == "ok"
    assert denied.ok is False
    assert denied.error is not None and denied.error.code == ToolErrorCode.IRREVERSIBLE_BLOCKED
    assert asked == ["tools.web_fetch", "tools.web_fetch"]


def test_confirm_gate_fail_closed_without_approver() -> None:
    """确认门 confirm 且无审批通道：直接 fail-closed 拒绝。"""
    resolver = CoeffectResolver()
    resolver.register("network:outbound", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    provider.register(web_fetch())
    result = provider.invoke("tools.web_fetch", {"url": "https://a.example"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None and result.error.code == ToolErrorCode.IRREVERSIBLE_BLOCKED


# ---- 校验口径单一真源（change 0059 / 账本 E14） ----


def test_type_matcher_has_single_implementation() -> None:
    """校验原语只有一份实现：工具层不得再持有 `_matches_type` 副本。"""
    assert not hasattr(provider_module, "_matches_type")


@pytest.mark.parametrize(
    ("args", "expected_message"),
    [
        ({}, "缺少必需参数: ['text']"),
        ({"text": 1}, "参数 text 类型不符，期望 string"),
    ],
)
def test_tool_layer_and_validator_agree_on_rejection(args, expected_message) -> None:
    """同一非法调用：工具层调用前校验与校验中间件给出同一口径的拒绝。"""
    provider = _provider()
    provider.register(_echo_tool())
    result = provider.invoke("test.echo", args, trace_id="t")
    assert result.error is not None and result.error.message == expected_message

    errors = Validator().validate_input("test.echo", args, _ECHO_SCHEMA)
    assert errors and errors[0] == expected_message


def test_tool_layer_and_validator_both_accept_valid_args() -> None:
    """合法调用两条路径都通过（委托不引入新拒绝）。"""
    provider = _provider()
    provider.register(_echo_tool())
    assert provider.invoke("test.echo", {"text": "hi"}, trace_id="t").ok is True
    assert Validator().validate_input("test.echo", {"text": "hi"}, _ECHO_SCHEMA) == []
