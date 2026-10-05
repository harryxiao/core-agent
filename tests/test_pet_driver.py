"""宿主驱动的唤醒节拍（change 0083 / 账本 E28）。

`0065`（账本 E17）裁决「唤醒由宿主驱动、内核不自建 daemon」；本模块是**宿主侧**的驱动薄壳：
逐会话 `wake()` + **故障隔离**（让行/退避/未激活 = 预期态静默跳过；意外异常记为失败但**不中断
其余宠物** —— 规格 R8「A 宠物异常不影响 B 宠物」）。节拍经注入 `sleep` 确定性验证。
"""

from __future__ import annotations

import pytest

from core.pet.core import PetError, PetErrorCode
from core.pet.core.driver import FAILED, SKIPPED, WOKEN, PetWakeDriver

_TWO_TICKS = 2


class _FakePet:
    """最小会话替身：只实现驱动消费的 `session_id` 与 `wake()`。"""

    def __init__(self, session_id: str, *, raises: Exception | None = None) -> None:
        self.session_id = session_id
        self.calls = 0
        self._raises = raises

    def wake(self) -> None:
        self.calls += 1
        if self._raises is not None:
            raise self._raises


def test_tick_wakes_every_registered_pet() -> None:
    first, second = _FakePet("a"), _FakePet("b")
    outcomes = PetWakeDriver(lambda: [first, second]).tick()
    assert [o.status for o in outcomes] == [WOKEN, WOKEN]
    assert first.calls == 1
    assert second.calls == 1


def test_tick_skips_expected_states_and_continues() -> None:
    """让行/退避/未激活是**预期态**（`PetError`）：跳过，但不影响其余宠物。"""
    yielding = _FakePet("yielding", raises=PetError(PetErrorCode.PET_YIELDING, "主循环 busy"))
    alive = _FakePet("alive")
    outcomes = PetWakeDriver(lambda: [yielding, alive]).tick()
    assert [o.status for o in outcomes] == [SKIPPED, WOKEN]
    assert "PET_YIELDING" in outcomes[0].reason
    assert "主循环 busy" in outcomes[0].reason
    assert alive.calls == 1


def test_tick_isolates_unexpected_failure() -> None:
    """规格 R8：A 宠物异常不影响 B 宠物（意外异常记为失败并继续）。"""
    broken = _FakePet("broken", raises=RuntimeError("loop 炸了"))
    healthy = _FakePet("healthy")
    outcomes = PetWakeDriver(lambda: [broken, healthy]).tick()
    assert [o.status for o in outcomes] == [FAILED, WOKEN]
    assert "loop 炸了" in outcomes[0].reason
    assert healthy.calls == 1


def test_run_drives_until_interrupted() -> None:
    """常驻节拍：每轮 `tick()` 后 `sleep(interval)`；`KeyboardInterrupt` 由调用方处理。"""
    pet = _FakePet("a")
    seen: list[int] = []

    def _sleep(_seconds: float) -> None:
        seen.append(pet.calls)
        if len(seen) == _TWO_TICKS:
            raise KeyboardInterrupt

    driver = PetWakeDriver(lambda: [pet], sleep=_sleep)
    with pytest.raises(KeyboardInterrupt):
        driver.run(0.5)
    assert seen == [1, _TWO_TICKS]  # 两轮各唤醒一次（第二轮前 sleep 抛出）
