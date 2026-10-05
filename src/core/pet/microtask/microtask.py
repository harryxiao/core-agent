"""日常随机微任务（pet-microtask）。

终端散步 / 系统小提示 / 无厘头注释；侵入性任务（无厘头注释）可配置关闭（R14）。

change 0087 / 账本 E26：三条任务各自有**真实来源**（命令历史条数 / 真实负载 / 真实写回），
**无真实产出 ⇒ `run()` 返回 `None`**（SHALL NOT 投出预制文案谎报）；`terminal_walk` 只报
**条数**、绝不外泄命令历史内容（历史可能含密钥/隐私）。探测函数可注入（测试确定性 / 生产缺省真探）。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（微任务）+ spec R14
"""

from __future__ import annotations

import os
import random
from collections.abc import Callable
from pathlib import Path

_WALK_TASK = "terminal_walk"
_HINT_TASK = "system_hint"
# 侵入性任务（可配置关闭）。
_INTRUSIVE_TASK = "nonsense_comment"

# 默认启用的微任务（不含侵入性任务）。
_DEFAULT_TASKS = {_WALK_TASK, _HINT_TASK}

_COMMENT_TEXT = "给代码加了一条无厘头注释。"


def _read_terminal_history(*, path: Path | None = None) -> int | None:
    """命令历史**非空行数**；文件不可读 / 无内容 ⇒ `None`（只返计数，绝不外泄内容）。"""
    if path is None:
        histfile = os.environ.get("HISTFILE")
        path = Path(histfile) if histfile else Path.home() / ".bash_history"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    count = sum(1 for line in text.splitlines() if line.strip())
    return count or None


def _system_hint(*, loadavg: float | None = None, cpus: int | None = None) -> str | None:
    """真实负载提示：1 分钟负载**不低于** CPU 数时才出声，否则 `None`（不打扰）。"""
    if loadavg is None:
        getter = getattr(os, "getloadavg", None)
        if getter is None:
            return None
        loadavg = float(getter()[0])
    threshold = cpus if cpus is not None else (os.cpu_count() or 1)
    if loadavg < threshold:
        return None
    return f"发现系统小提示：1 分钟负载 {loadavg:.2f} 已不低于 CPU 数 {threshold}，机器有点忙。"


class MicrotaskRunner:
    """日常随机微任务：只执行已启用任务，侵入性任务可配置关闭。

    每条任务产出**真实观测或真实副作用**；无真实产出 ⇒ `run()` 返回 `None`。
    探针可注入（`walk_probe` / `hint_probe`），缺省接真实探测函数。
    """

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        *,
        enabled: set[str] | None = None,
        intrusive: bool = False,
        comment_writer: Callable[[str], None] | None = None,
        walk_probe: Callable[[], int | None] | None = None,
        hint_probe: Callable[[], str | None] | None = None,
    ) -> None:
        self._enabled: set[str] = enabled if enabled is not None else set(_DEFAULT_TASKS)
        self._intrusive = intrusive
        self._comment_writer = comment_writer
        self._walk_probe = walk_probe if walk_probe is not None else _read_terminal_history
        self._hint_probe = hint_probe if hint_probe is not None else _system_hint

    def enabled_tasks(self) -> list[str]:
        """当前已启用任务清单（侵入性任务受 intrusive 总开关控制）。"""
        tasks = set(self._enabled)
        if self._intrusive:
            tasks.add(_INTRUSIVE_TASK)
        else:
            tasks.discard(_INTRUSIVE_TASK)
        return sorted(tasks)

    def run(self, task_id: str | None = None) -> str | None:
        """执行一个已启用微任务；指定 task_id 时确定性执行，缺省随机；无真实产出 ⇒ `None`。"""
        enabled = self.enabled_tasks()
        if not enabled:
            return None
        chosen = task_id if task_id is not None else random.choice(enabled)
        if chosen not in enabled:
            return None
        return self._perform(chosen)

    def _perform(self, task_id: str) -> str | None:
        """按任务取真实产出：观测不成立 / 无写回口 ⇒ `None`（不谎报）。"""
        if task_id == _WALK_TASK:
            count = self._walk_probe()
            if count is None:
                return None
            return f"在终端里散了一圈步：读过 {count} 条命令历史（只计条数）。"
        if task_id == _HINT_TASK:
            return self._hint_probe()
        if self._comment_writer is None:
            return None
        self._comment_writer(_COMMENT_TEXT)
        return _COMMENT_TEXT
