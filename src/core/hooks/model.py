"""钩子事件模型与载荷脱敏（change 0269）。

事件词表与载荷字段是**契约**（`doc/openspec/specs/hooks/spec.md`）；本模块只做
「事件对象 + 摘要 + 脱敏」，不执行任何外部命令。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from core.memory import redact_secrets

HOOK_EVENTS: tuple[str, ...] = (
    "session.start",
    "session.end",
    "turn.before",
    "turn.after",
    "tool.before",
    "tool.after",
    "memory.write",
)

# before 类可否决：退出码非 0 / 回调返回 False ⇒ 阻断。
BEFORE_EVENTS: frozenset[str] = frozenset({"turn.before", "tool.before"})

ON_ERROR_POLICIES: tuple[str, ...] = ("block", "allow", "warn")

MAX_TIMEOUT_S = 60.0
MAX_PAYLOAD_CHARS = 4096
REDACTED = "<redacted>"


@dataclass(frozen=True)
class HookEvent:
    """一次投递给钩子的事件（值已在构造前脱敏）。"""

    name: str
    payload: dict[str, Any]
    ts: float = field(default_factory=time.time)

    def envelope(self) -> dict[str, Any]:
        """外部命令 stdin 的 JSON 信封。"""
        return {"event": self.name, "payload": self.payload, "ts": self.ts}


HookCallback = Callable[[HookEvent], bool]


@dataclass(frozen=True)
class HookEntry:
    """一条已校验的钩子声明：外部命令或内置回调二选一。"""

    event: str
    command: tuple[str, ...] | None = None
    callback: HookCallback | None = None
    timeout_s: float = 5.0
    on_error: str = "block"
    match: dict[str, Any] = field(default_factory=dict[str, Any])
    name: str = ""

    @property
    def label(self) -> str:
        """trace 用标识：命令只留 basename（不留完整 argv）。"""
        if self.name:
            return self.name
        if self.command:
            executable = os.path.basename(self.command[0].replace("\\", "/"))
            return executable or "command"
        return "callback"

    def matches(self, payload: dict[str, Any]) -> bool:
        """可选收窄：`match` 中每个字段都与载荷同值才命中（缺省空 ⇒ 全量）。"""
        return all(str(payload.get(key)) == str(value) for key, value in self.match.items())


def digest(value: Any) -> dict[str, Any]:
    """参数 / 结果摘要：只给长度 + sha256 前缀，绝不给正文。"""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "chars": len(text),
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
    }


def redact_payload(value: Any, secrets: tuple[str, ...]) -> Any:
    """递归脱敏载荷：正则密钥形态 + 运行期登记明文 → ``<redacted>``。

    单字符串截断到 ``MAX_PAYLOAD_CHARS``（有界信封）；dict 键原样保留（键不含取值）。
    """
    if isinstance(value, str):
        cleaned = redact_secrets(value)
        for secret in secrets:
            if secret:
                cleaned = cleaned.replace(secret, REDACTED)
        return cleaned[:MAX_PAYLOAD_CHARS]
    if isinstance(value, dict):
        nested = cast("dict[str, Any]", value)
        return {key: redact_payload(item, secrets) for key, item in nested.items()}
    if isinstance(value, list):
        return [redact_payload(item, secrets) for item in cast("list[Any]", value)]
    if isinstance(value, tuple):
        return [redact_payload(item, secrets) for item in cast("tuple[Any, ...]", value)]
    return value
