"""可逆效应追踪（EffectTracker）。

所有写操作必须 ``record(effect)``，携带撤销闭包 ``undo``；``rollback`` 按
trace_id 分组的 undo 栈逆序撤销，支持按轮回滚或全局回滚，是「可观测性 /
进化回滚」的根基（ADR-0002：副作用一律建模为可逆效应）。

线程安全：并发 record / rollback 经 ``threading.RLock`` 串行化，避免半记录
或半回滚状态。

对应接口：doc/03-interfaces/plugin-registry-interface.md §4
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Effect:
    """一条可逆副作用记录。"""

    op: str  # "file_write" / "proc_start" / ...
    target: str  # 作用对象
    undo: Callable[[], None]  # 撤销闭包
    reversible: bool
    coeffect: list[str]
    trace_id: str
    ts: float


EffectId = str


@dataclass
class RollbackReport:
    """一次回滚的结果：成功撤销与撤销失败（进入 QUARANTINE）分别汇总。"""

    reverted: list[EffectId] = field(default_factory=list[EffectId])
    undo_failed: list[EffectId] = field(default_factory=list[EffectId])


class EffectTracker:
    """维护可逆效应记录及其 undo 栈，支持按 trace 或全局回滚。"""

    def __init__(self) -> None:
        self._effects: dict[EffectId, Effect] = {}
        self._by_trace: dict[str, list[EffectId]] = {}
        self._lock = threading.RLock()

    def record(self, effect: Effect) -> EffectId:
        """记录一条可逆效应，返回其句柄。"""
        effect_id = uuid.uuid4().hex
        with self._lock:
            self._effects[effect_id] = effect
            self._by_trace.setdefault(effect.trace_id, []).append(effect_id)
        return effect_id

    def rollback(self, trace_id: str | None = None) -> RollbackReport:
        """回滚：按 ``trace_id`` 逆序撤销该轮效应；``None`` 则全局回滚。"""
        with self._lock:
            if trace_id is None:
                ordered = list(self._effects)
            else:
                ordered = list(self._by_trace.get(trace_id, []))
        report = RollbackReport()
        for effect_id in reversed(ordered):
            effect = self._effects[effect_id]
            if not effect.reversible:
                continue
            try:
                effect.undo()
                report.reverted.append(effect_id)
            except Exception:  # noqa: BLE001 — 撤销失败不中断，计入 QUARANTINE
                report.undo_failed.append(effect_id)
        return report

    def replay(self, effect_id: EffectId) -> Effect:
        """返回效应记录，供可观测性复现（Effect 仅携带撤销闭包，无重放入口）。"""
        with self._lock:
            return self._effects[effect_id]

    def audit(self, trace_id: str) -> list[Effect]:
        """返回某轮的全部效应记录（按记录序）。"""
        with self._lock:
            return [self._effects[eid] for eid in self._by_trace.get(trace_id, [])]
