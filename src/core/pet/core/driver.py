"""宿主侧的唤醒节拍：逐会话 `wake()` + 故障隔离（change 0083 / 账本 E28）。

`0065`（账本 E17）裁决「周期触发由宿主驱动、内核不自建调度线程」；本模块是**宿主侧**的薄壳，
只做三件事：按可注入的 `sleep` 打节拍、逐会话唤醒、把每只宠物的结局记成结构化 `WakeOutcome`。
它**不打印、不落盘、不吞异常** —— 呈现与退出码归调用方（CLI）。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from .errors import PetError

WOKEN = "woken"
"""唤醒已驱动（`wake()` 正常返回）。"""

SKIPPED = "skipped"
"""预期态静默跳过（让行 / 退避 / 未激活 —— `PetError`，设计中的常态）。"""

FAILED = "failed"
"""意外失败（非 `PetError`）：记下原因并**继续**其余宠物（规格 R8）。"""


class WakingSession(Protocol):
    """驱动只依赖这两个成员，故会话与测试替身皆可直接驱动。"""

    session_id: str

    # 返回 `object`：驱动只取其副作用（唤醒一次），返回值形态归会话自定
    # （`PetSession.wake()` 返回 `LoopResult`，测试替身返回 `None`）。
    def wake(self) -> object: ...


@dataclass(frozen=True)
class WakeOutcome:
    """一只宠物一轮的结局（`status` ∈ `WOKEN`/`SKIPPED`/`FAILED`）。"""

    session_id: str
    status: str
    reason: str = ""


class PetWakeDriver:
    """常驻唤醒节拍：`tick()` 一轮，`run()` 无限循环。

    `sessions` 是**可调用体**（如 `PetManager.list`）而非快照 —— 每轮重取，
    故驱动期间新注册的宠物自动纳入。
    """

    def __init__(
        self,
        sessions: Callable[[], Iterable[WakingSession]],
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sessions = sessions
        self._sleep = sleep

    def tick(self) -> list[WakeOutcome]:
        """驱动一轮：逐会话唤醒，返回每只宠物的结局（顺序同注册序）。"""
        outcomes: list[WakeOutcome] = []
        for session in list(self._sessions()):
            try:
                session.wake()
            except PetError as exc:
                outcomes.append(WakeOutcome(session.session_id, SKIPPED, str(exc)))
            except Exception as exc:  # noqa: BLE001 — R8：单宠物意外失败不中断其余
                reason = f"{type(exc).__name__}: {exc}"
                outcomes.append(WakeOutcome(session.session_id, FAILED, reason))
            else:
                outcomes.append(WakeOutcome(session.session_id, WOKEN))
        return outcomes

    def run(
        self,
        interval: float,
        *,
        on_tick: Callable[[list[WakeOutcome]], None] | None = None,
    ) -> None:
        """常驻循环：`tick()` → `on_tick(...)` → `sleep(interval)` → …。

        `KeyboardInterrupt` 不在此吞掉，上抛给调用方。
        """
        while True:
            outcomes = self.tick()
            if on_tick is not None:
                on_tick(outcomes)
            self._sleep(interval)
