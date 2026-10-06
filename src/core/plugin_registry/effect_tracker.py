"""可逆效应追踪（EffectTracker）。

所有写操作必须 ``record(effect)``，携带撤销闭包 ``undo``；``rollback`` 按
trace_id 分组的 undo 栈逆序撤销，支持按轮回滚或全局回滚，是「可观测性 /
进化回滚」的根基（ADR-0002：副作用一律建模为可逆效应）。

回滚**清账**（ADR-0121）：撤销成功的效应随即出账，因此同一 trace 重复回滚
不会二次撤销、账目不会无界增长；撤销**失败**者留账隔离（由 ``undo_failed``
报告，不静默丢弃）；``clear`` 提供只清账、不撤销的显式入口。

线程安全：并发 record / rollback / clear 经 ``threading.RLock`` 串行化，避免
半记录或半回滚状态；undo 闭包在**不持锁**处调用（可重入 tracker 不死锁）。

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
        """回滚：按 ``trace_id`` 逆序撤销该轮效应；``None`` 则全局回滚。

        撤销**成功**的效应随即出账，不可逆效应不撤销亦出账；撤销**失败**者留账隔离
        （见 ``audit``）。故同一 trace 重复回滚不会二次撤销、账目不会无界增长。
        """
        with self._lock:
            if trace_id is None:
                ordered = list(self._effects)
            else:
                ordered = list(self._by_trace.get(trace_id, []))
        report = RollbackReport()
        for effect_id in reversed(ordered):
            effect = self._effects[effect_id]
            if not effect.reversible:
                self._forget(effect_id)
                continue
            try:
                effect.undo()
            except Exception:  # noqa: BLE001 — 撤销失败不中断，计入 QUARANTINE
                report.undo_failed.append(effect_id)
                continue
            self._forget(effect_id)
            report.reverted.append(effect_id)
        with self._lock:
            self._prune_traces()
        return report

    def clear(self, trace_id: str | None = None) -> None:
        """显式清账：按 ``trace_id`` 移除该轮效应；``None`` 则清空全局。

        只移除账目，**不**调用任何 ``undo``（供调用方已另行恢复现场时丢弃账目）。
        """
        with self._lock:
            if trace_id is None:
                self._effects.clear()
                self._by_trace.clear()
                return
            doomed = [eid for eid, e in self._effects.items() if e.trace_id == trace_id]
            for effect_id in doomed:
                del self._effects[effect_id]
            self._by_trace.pop(trace_id, None)

    def _forget(self, effect_id: EffectId) -> None:
        """把一条效应移出 ``_effects``（trace 映射由 ``_prune_traces`` 统一清理）。"""
        with self._lock:
            self._effects.pop(effect_id, None)

    def _prune_traces(self) -> None:
        """清理 trace 映射：剔除已出账的 EffectId，空 trace 键一并删除。"""
        with self._lock:
            pruned = {
                trace_id: [eid for eid in eids if eid in self._effects]
                for trace_id, eids in self._by_trace.items()
            }
            self._by_trace = {trace_id: eids for trace_id, eids in pruned.items() if eids}

    def replay(self, effect_id: EffectId) -> Effect:
        """返回效应记录，供可观测性复现（Effect 仅携带撤销闭包，无重放入口）。"""
        with self._lock:
            return self._effects[effect_id]

    def audit(self, trace_id: str) -> list[Effect]:
        """返回某轮**尚未了结**的效应记录（按记录序）：回滚成功后为空（清账）。"""
        with self._lock:
            return [self._effects[eid] for eid in self._by_trace.get(trace_id, [])]
