"""日常随机微任务（pet-microtask）。

终端散步 / 系统小提示 / 无厘头注释；侵入性任务（无厘头注释）可配置关闭
（R14）。无厘头注释经 comment_writer 注入 git 写回，deferred。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（微任务）+ spec R14
"""

from __future__ import annotations

import random
from collections.abc import Callable

# 默认启用的微任务（不含侵入性任务）。
_DEFAULT_TASKS = {"terminal_walk", "system_hint"}
# 侵入性任务（可配置关闭）。
_INTRUSIVE_TASK = "nonsense_comment"

_TASK_DESCRIPTIONS = {
    "terminal_walk": "在终端里散了一圈步，看了看最近的命令历史。",
    "system_hint": "发现一条系统小提示：记得给核心依赖升个版本。",
    "nonsense_comment": "给代码加了一条无厘头注释。",
}


class MicrotaskRunner:
    """日常随机微任务：只执行已启用任务，侵入性任务可配置关闭。"""

    def __init__(
        self,
        *,
        enabled: set[str] | None = None,
        intrusive: bool = False,
        comment_writer: Callable[[str], None] | None = None,
    ) -> None:
        self._enabled: set[str] = enabled if enabled is not None else set(_DEFAULT_TASKS)
        self._intrusive = intrusive
        self._comment_writer = comment_writer

    def enabled_tasks(self) -> list[str]:
        """当前已启用任务清单（侵入性任务受 intrusive 总开关控制）。"""
        tasks = set(self._enabled)
        if self._intrusive:
            tasks.add(_INTRUSIVE_TASK)
        else:
            tasks.discard(_INTRUSIVE_TASK)
        return sorted(tasks)

    def run(self, task_id: str | None = None) -> str | None:
        """执行一个已启用微任务；指定 task_id 时确定性执行，缺省随机。"""
        enabled = self.enabled_tasks()
        if not enabled:
            return None
        chosen = task_id if task_id is not None else random.choice(enabled)
        if chosen not in enabled:
            return None
        if chosen == _INTRUSIVE_TASK and self._comment_writer is not None:
            self._comment_writer(_TASK_DESCRIPTIONS[chosen])
        return _TASK_DESCRIPTIONS.get(chosen)
