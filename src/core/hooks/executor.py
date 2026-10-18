"""钩子执行器（change 0269）：argv 子进程 + 内置回调。

安全边界（规格「钩子失败处置与安全边界」）：
- argv 列表、**不经 shell**；stdin 收一个 JSON 信封后 EOF；
- 子进程**白名单环境**（不继承父进程密钥）；
- stdout / stderr 只读取后丢弃（有界捕获），绝不外传；
- 每次调用回一个结构化结局，由管理器翻译成放行 / 阻断 / 留痕。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass

from .model import HookEntry, HookEvent

# 白名单环境：只保留进程启动与本地化所需的最小集合（Windows 另需 SYSTEMROOT 等）。
_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "USERPROFILE",
)


@dataclass(frozen=True)
class HookOutcome:
    """一次钩子调用的结局（不含正文，最多留退出码）。"""

    kind: str  # allow / block / error / timeout
    exit_code: int | None
    duration_ms: float


def _hook_env() -> dict[str, str]:
    return {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}


def run_entry(entry: HookEntry, event: HookEvent) -> HookOutcome:
    """执行一条钩子；任何失败都收敛为 outcome，不向调用方抛异常。"""
    started = time.perf_counter()
    if entry.callback is not None:
        try:
            allowed = entry.callback(event)
        except Exception:  # noqa: BLE001 — 回调异常按 on_error 处置（由管理器决定）
            return HookOutcome("error", None, _elapsed_ms(started))
        return HookOutcome(
            "allow" if allowed else "block", 0 if allowed else 1, _elapsed_ms(started)
        )

    argv = list(entry.command or ())
    if not argv:
        return HookOutcome("error", None, _elapsed_ms(started))
    stdin = json.dumps(event.envelope(), ensure_ascii=False).encode("utf-8")
    try:
        completed = subprocess.run(  # noqa: S603 — argv 列表、不经 shell，属显式设计
            argv,
            input=stdin,
            capture_output=True,
            timeout=entry.timeout_s,
            env=_hook_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return HookOutcome("timeout", None, _elapsed_ms(started))
    except OSError:
        return HookOutcome("error", None, _elapsed_ms(started))
    kind = "allow" if completed.returncode == 0 else "block"
    return HookOutcome(kind, completed.returncode, _elapsed_ms(started))


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
