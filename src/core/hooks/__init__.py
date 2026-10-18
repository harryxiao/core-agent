"""钩子（Hooks）：声明式生命周期扩展点（change 0269 / ADR-0259）。

契约见 `doc/openspec/specs/hooks/spec.md`；本包只提供事件模型、执行器与注册表，
由组合根接到 loop / memory 的既有接缝上。
"""

from .manager import HookManager, entries_from_config
from .model import (
    BEFORE_EVENTS,
    HOOK_EVENTS,
    MAX_TIMEOUT_S,
    ON_ERROR_POLICIES,
    REDACTED,
    HookCallback,
    HookEntry,
    HookEvent,
    digest,
    redact_payload,
)

__all__ = [
    "BEFORE_EVENTS",
    "HOOK_EVENTS",
    "MAX_TIMEOUT_S",
    "ON_ERROR_POLICIES",
    "REDACTED",
    "HookCallback",
    "HookEntry",
    "HookEvent",
    "HookManager",
    "digest",
    "entries_from_config",
    "redact_payload",
]
