"""钩子注册表与管理器（change 0269）。

按事件与 `match` 收窄后**按声明序**执行；before 类任一失败（按 `on_error`）即阻断，
after 类异常只留痕。每次调用落 ``kind="hook"`` trace —— 载荷只有事件名、命令 basename、
退出码、时长与 ``blocked_by``，**不含** argv / 输出正文 / 事件载荷。
"""

from __future__ import annotations

import asyncio
import atexit
import time
import uuid
import warnings
from typing import Any, cast

from core.observability import TraceEvent, Tracer

from .executor import HookOutcome, run_entry
from .model import (
    HOOK_EVENTS,
    MAX_TIMEOUT_S,
    ON_ERROR_POLICIES,
    HookCallback,
    HookEntry,
    HookEvent,
    digest,
    redact_payload,
)

_DEFAULT_TIMEOUT_S = 5.0


def _clamp_timeout(value: Any, default: float) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        warnings.warn(f"非法钩子超时: {value!r}（回落 {default}s）", UserWarning, stacklevel=3)
        return default
    if seconds <= 0:
        warnings.warn(f"非法钩子超时: {value!r}（回落 {default}s）", UserWarning, stacklevel=3)
        return default
    if seconds > MAX_TIMEOUT_S:
        warnings.warn(
            f"钩子超时 {seconds}s 超过硬上限，按 {MAX_TIMEOUT_S}s 截断",
            UserWarning,
            stacklevel=3,
        )
        return MAX_TIMEOUT_S
    return seconds


def entries_from_config(
    raw_entries: Any,
    *,
    default_timeout_s: float = _DEFAULT_TIMEOUT_S,
    default_on_error: str = "block",
) -> list[HookEntry]:
    """把 ``hooks.entries`` 原始清单校验为 ``HookEntry``；非法项告警并跳过（fail-closed）。"""
    if raw_entries is None:
        return []
    if not isinstance(raw_entries, list):
        warnings.warn("hooks.entries 须为清单；已忽略", UserWarning, stacklevel=2)
        return []
    entries: list[HookEntry] = []
    for raw_item in cast("list[Any]", raw_entries):
        if not isinstance(raw_item, dict):
            warnings.warn("钩子条目须为映射；已跳过", UserWarning, stacklevel=2)
            continue
        item = cast("dict[str, Any]", raw_item)
        event = str(item.get("event", ""))
        if event not in HOOK_EVENTS:
            warnings.warn(f"未知钩子事件: {event!r}；已跳过", UserWarning, stacklevel=2)
            continue
        command = item.get("command")
        if not isinstance(command, list) or not command:
            warnings.warn(
                f"钩子 {event} 的 command 须为非空字符串列表；已跳过", UserWarning, stacklevel=2
            )
            continue
        parts = cast("list[Any]", command)
        if not all(isinstance(part, str) and part for part in parts):
            warnings.warn(
                f"钩子 {event} 的 command 须为非空字符串列表；已跳过", UserWarning, stacklevel=2
            )
            continue
        argv = tuple(cast("list[str]", command))
        on_error = str(item.get("on_error", default_on_error))
        if on_error not in ON_ERROR_POLICIES:
            warnings.warn(
                f"非法钩子 on_error: {on_error!r}（回落 block）", UserWarning, stacklevel=2
            )
            on_error = "block"
        match = item.get("match", {})
        if not isinstance(match, dict):
            warnings.warn(
                f"钩子 {event} 的 match 须为映射；已按全量处理", UserWarning, stacklevel=2
            )
            match = {}
        entries.append(
            HookEntry(
                event=event,
                command=argv,
                timeout_s=_clamp_timeout(
                    item.get("timeout_s", default_timeout_s), default_timeout_s
                ),
                on_error=on_error,
                match=dict(cast("dict[str, Any]", match)),
                name=str(item.get("name", "")),
            )
        )
    return entries


class HookManager:
    """钩子注册与分派。`enabled` 缺省关闭由组合根决定是否构造条目。"""

    def __init__(
        self,
        entries: list[HookEntry] | None = None,
        *,
        tracer: Tracer | None = None,
        mode: str = "runtime",
        default_timeout_s: float = _DEFAULT_TIMEOUT_S,
        default_on_error: str = "block",
    ) -> None:
        self._entries: list[HookEntry] = list(entries or [])
        self._tracer = tracer
        self._mode = mode
        self._default_timeout_s = default_timeout_s
        self._default_on_error = (
            default_on_error if default_on_error in ON_ERROR_POLICIES else "block"
        )
        self._secrets: list[str] = []
        self._sessions: set[str] = set()
        self._closed = False
        if self._entries:
            atexit.register(self.close)

    @property
    def enabled(self) -> bool:
        return bool(self._entries)

    def register_secret(self, value: str) -> None:
        """登记明文密钥：载荷出进程前逐字替换为 ``<redacted>``。"""
        if value and value not in self._secrets:
            self._secrets.append(value)

    def register_callback(  # noqa: PLR0913 — 可选注入面均为 keyword-only
        self,
        event: str,
        callback: HookCallback,
        *,
        match: dict[str, Any] | None = None,
        timeout_s: float | None = None,
        on_error: str | None = None,
        name: str = "",
    ) -> None:
        """组合根注入内置回调（与外部命令同一失败语义）。"""
        if event not in HOOK_EVENTS:
            raise ValueError(f"未知钩子事件: {event!r}")  # noqa: TRY003
        self._entries.append(
            HookEntry(
                event=event,
                callback=callback,
                timeout_s=(
                    self._default_timeout_s
                    if timeout_s is None
                    else _clamp_timeout(timeout_s, self._default_timeout_s)
                ),
                on_error=on_error if on_error in ON_ERROR_POLICIES else self._default_on_error,
                match=dict(match or {}),
                name=name,
            )
        )
        if len(self._entries) == 1:
            atexit.register(self.close)

    # ---- 事件入口（before 类可否决，after 类只留痕） ----

    async def start_session(self, session_id: str) -> None:
        if self._closed or session_id in self._sessions:
            return
        self._sessions.add(session_id)
        payload = {"session_id": session_id, "mode": self._mode}
        await asyncio.to_thread(self._dispatch_after, "session.start", payload, trace_id="")

    def end_session(self, session_id: str, reason: str) -> None:
        if session_id not in self._sessions:
            return
        self._sessions.discard(session_id)
        payload = {
            "session_id": session_id,
            "mode": self._mode,
            "reason": reason,
        }
        self._dispatch_after("session.end", payload, trace_id="")

    def close(self) -> None:
        """进程退出收尾：对每个活跃会话投递一次 ``session.end``（幂等）。"""
        if self._closed:
            return
        self._closed = True
        for session_id in sorted(self._sessions):
            self.end_session(session_id, "exit")

    async def before_turn(self, session_id: str, trace_id: str, turn_index: int, text: str) -> bool:
        payload = {
            "session_id": session_id,
            "trace_id": trace_id,
            "turn_index": turn_index,
            "input": text,
        }
        return await asyncio.to_thread(self._dispatch_before, "turn.before", payload, trace_id)

    async def after_turn(self, session_id: str, trace_id: str, ok: bool, steps: int) -> None:
        payload = {
            "session_id": session_id,
            "trace_id": trace_id,
            "ok": ok,
            "steps": steps,
        }
        await asyncio.to_thread(self._dispatch_after, "turn.after", payload, trace_id)

    async def before_tool(
        self, tool_id: str, args: dict[str, Any], session_id: str, trace_id: str
    ) -> bool:
        payload = {
            "tool_id": tool_id,
            "args_digest": digest(args),
            "decision": "pending",
        }
        return await asyncio.to_thread(self._dispatch_before, "tool.before", payload, trace_id)

    async def after_tool(self, tool_id: str, result: Any, session_id: str, trace_id: str) -> None:
        payload = {
            "tool_id": tool_id,
            "ok": not bool(getattr(result, "failed", False)),
            "result_digest": digest(
                getattr(result, "error", "")
                if getattr(result, "failed", False)
                else getattr(result, "data", None)
            ),
            "duration_ms": int(getattr(result, "duration_ms", 0)),
        }
        await asyncio.to_thread(self._dispatch_after, "tool.after", payload, trace_id)

    def memory_write(self, layer: str, entry: Any) -> None:
        """记忆写入观察者（同步入口；不可否决、异常吞掉）。"""
        payload = {
            "layer": layer,
            "entry_id": str(getattr(entry, "id", "")),
            "kind": str(getattr(entry, "kind", "")),
            "bytes": len(str(getattr(entry, "content", "")).encode("utf-8")),
        }
        self._dispatch_after("memory.write", payload, trace_id=str(getattr(entry, "trace_id", "")))

    # ---- 内部：分派 / 处置 / 留痕 ----

    def _entries_for(self, event: str, payload: dict[str, Any]) -> list[HookEntry]:
        return [entry for entry in self._entries if entry.event == event and entry.matches(payload)]

    def _dispatch_before(self, event: str, payload: dict[str, Any], trace_id: str) -> bool:
        safe = redact_payload(payload, tuple(self._secrets))
        for entry in self._entries_for(event, safe):
            outcome = run_entry(entry, HookEvent(event, safe))
            if outcome.kind == "allow":
                self._record(event, entry, outcome, trace_id, None)
                continue
            if outcome.kind == "block":
                self._record(event, entry, outcome, trace_id, entry.label)
                return False
            if entry.on_error == "allow":
                self._record(event, entry, outcome, trace_id, None)
                continue
            if entry.on_error == "warn":
                warnings.warn(
                    f"钩子 {event} 执行异常（{outcome.kind}），按 on_error=warn 放行",
                    UserWarning,
                    stacklevel=2,
                )
                self._record(event, entry, outcome, trace_id, None)
                continue
            self._record(event, entry, outcome, trace_id, entry.label)
            return False
        return True

    def _dispatch_after(self, event: str, payload: dict[str, Any], trace_id: str) -> None:
        safe = redact_payload(payload, tuple(self._secrets))
        for entry in self._entries_for(event, safe):
            outcome = run_entry(entry, HookEvent(event, safe))
            self._record(event, entry, outcome, trace_id, None)

    def _record(
        self,
        event: str,
        entry: HookEntry,
        outcome: HookOutcome,
        trace_id: str,
        blocked_by: str | None,
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        payload: dict[str, Any] = {
            "event": event,
            "command": entry.label,
            "exit": outcome.exit_code,
            "duration_ms": outcome.duration_ms,
        }
        if blocked_by is not None:
            payload["blocked_by"] = blocked_by
        ephemeral = not trace_id or not tracer.is_active(trace_id)
        target = trace_id
        if ephemeral:
            target = tracer.start_trace(f"hook.{event}")
        tracer.record(
            TraceEvent(
                trace_id=target,
                span_id=uuid.uuid4().hex,
                ts=time.time(),
                kind="hook",
                payload=payload,
            )
        )
        if ephemeral:
            tracer.end_trace(target)
