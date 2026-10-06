"""plugin-registry 单元测试（对齐规格场景 + M0 验收）。

覆盖 spec/plugin-registry 的场景：
- 注册并校验 / 卸载干净 / 并发热插拔原子性 / 注册超时
- 依赖满足 / 循环依赖检测
- 能力边界 / 插件崩溃隔离
以及 EffectTracker（清账与幂等）/ CoeffectResolver 的可逆效应与密钥句柄语义。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.plugin_registry import (
    CoeffectMissing,
    CoeffectResolver,
    DomainError,
    Effect,
    EffectTracker,
    ErrorCode,
    PluginRegistry,
    PluginState,
    SecretRef,
)


class _FakePlugin:
    """满足 Plugin 结构契约的最小测试插件。"""

    def __init__(  # noqa: PLR0913, PLR0917 — 测试桩，参数皆为可选的注入行为
        self,
        plugin_id: str,
        generation: int = 0,
        deps: list[str] | None = None,
        coeffects: list[str] | None = None,
        load_raises: Exception | None = None,
        load_sleep: float | None = None,
        load_order: list[str] | None = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.generation = generation
        self.schema: dict = {"type": "object"}
        self.coeffects = coeffects or []
        self.deps = deps or []
        self._load_raises = load_raises
        self._load_sleep = load_sleep
        self._load_order = load_order
        self.loaded = False

    def load(self) -> None:
        if self._load_sleep is not None:
            time.sleep(self._load_sleep)
        if self._load_raises is not None:
            raise self._load_raises
        if self._load_order is not None:
            self._load_order.append(self.plugin_id)
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def check(self) -> bool:
        return True


def test_register_and_unload_no_residue() -> None:
    registry = PluginRegistry()
    plugin = _FakePlugin("tools.code_run")
    registry.register(plugin)
    assert registry.state("tools.code_run") is PluginState.REGISTERED
    registry.load("tools.code_run")
    assert registry.state("tools.code_run") is PluginState.LOADED
    assert plugin.loaded is True
    registry.unload("tools.code_run")
    assert registry.get("tools.code_run") is None
    assert registry.state("tools.code_run") is PluginState.UNLOADED
    assert "tools.code_run" not in registry.list_ids()


def test_concurrent_hotswap_no_residue() -> None:
    registry = PluginRegistry()
    count = 1000

    def worker(i: int) -> None:
        plugin_id = f"test.plugin{i}"
        registry.register(_FakePlugin(plugin_id))
        registry.load(plugin_id)
        registry.unload(plugin_id)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(worker, range(count)))
    assert registry.list_ids() == []


def test_circular_dependency_rejected() -> None:
    registry = PluginRegistry()
    registry.register(_FakePlugin("a", deps=["b"]))
    with pytest.raises(DomainError) as exc_info:
        registry.register(_FakePlugin("b", deps=["a"]))
    assert exc_info.value.code is ErrorCode.CIRCULAR_DEPENDENCY


def test_dependency_load_order() -> None:
    order: list[str] = []
    registry = PluginRegistry()
    registry.register(_FakePlugin("a", deps=["b"], load_order=order))
    registry.register(_FakePlugin("b", load_order=order))
    registry.load("a")
    assert order == ["b", "a"]


def test_generation_conflict() -> None:
    registry = PluginRegistry()
    registry.register(_FakePlugin("a", generation=2))
    with pytest.raises(DomainError) as exc_info:
        registry.register(_FakePlugin("a", generation=1))
    assert exc_info.value.code is ErrorCode.GENERATION_CONFLICT


def test_register_timeout() -> None:
    registry = PluginRegistry()
    registry.register(_FakePlugin("slow", load_sleep=1.0))
    with pytest.raises(DomainError) as exc_info:
        registry.load("slow", timeout=0.05)
    assert exc_info.value.code is ErrorCode.REGISTER_TIMEOUT
    assert registry.state("slow") is PluginState.FAULTED


def test_crash_isolation() -> None:
    registry = PluginRegistry()
    registry.register(_FakePlugin("bad", load_raises=RuntimeError("boom")))
    registry.register(_FakePlugin("good"))
    with pytest.raises(DomainError) as exc_info:
        registry.load("bad")
    assert exc_info.value.code is ErrorCode.NOT_ACTIVE
    assert registry.state("bad") is PluginState.FAULTED
    registry.load("good")  # 宿主与其余插件不受影响
    assert registry.state("good") is PluginState.LOADED


def _effect(
    target: str,
    *,
    trace_id: str,
    undo: Callable[[], None] | None = None,
    reversible: bool = True,
) -> Effect:
    """构造一条可逆效应；``undo`` 缺省为空操作。"""
    return Effect(
        op="file_write",
        target=target,
        undo=undo if undo is not None else (lambda: None),
        reversible=reversible,
        coeffect=["filesystem:write"],
        trace_id=trace_id,
        ts=1.0,
    )


def _recorder(seen: list[str], name: str) -> Callable[[], None]:
    def undo() -> None:
        seen.append(name)

    return undo


def test_effect_tracker_rollback_and_audit() -> None:
    tracker = EffectTracker()
    applied: list[str] = []

    def make_undo(name: str):
        def undo() -> None:
            applied.append(name)

        return undo

    e1 = tracker.record(
        Effect(
            op="file_write",
            target="a",
            undo=make_undo("a"),
            reversible=True,
            coeffect=["filesystem:write"],
            trace_id="t1",
            ts=1.0,
        )
    )
    e2 = tracker.record(
        Effect(
            op="file_write",
            target="b",
            undo=make_undo("b"),
            reversible=True,
            coeffect=["filesystem:write"],
            trace_id="t1",
            ts=2.0,
        )
    )
    assert tracker.audit("t1") == [tracker.replay(e1), tracker.replay(e2)]
    report = tracker.rollback("t1")
    assert applied == ["b", "a"]  # 逆序撤销
    assert set(report.reverted) == {e1, e2}
    assert tracker.audit("t1") == []  # 撤销成功即出账（change 0128）


def test_rollback_clears_ledger_and_is_idempotent() -> None:
    """回滚后账目清空 ⇒ 同一 trace 重复回滚不二次撤销（change 0128 / E67）。"""
    tracker = EffectTracker()
    applied: list[str] = []
    tracker.record(_effect("a", trace_id="t1", undo=_recorder(applied, "a")))
    tracker.record(_effect("b", trace_id="t1", undo=_recorder(applied, "b")))

    first = tracker.rollback("t1")
    assert applied == ["b", "a"]
    assert first.undo_failed == []
    assert len(first.reverted) == len(applied)
    assert tracker.audit("t1") == []

    second = tracker.rollback("t1")
    assert second.reverted == []
    assert second.undo_failed == []
    assert applied == ["b", "a"]


def test_rollback_clears_all_traces_globally() -> None:
    tracker = EffectTracker()
    tracker.record(_effect("a", trace_id="t1"))
    tracker.record(_effect("b", trace_id="t2"))

    tracker.rollback()
    assert tracker.audit("t1") == []
    assert tracker.audit("t2") == []


def test_rollback_is_trace_scoped() -> None:
    tracker = EffectTracker()
    tracker.record(_effect("a", trace_id="t1"))
    kept = tracker.record(_effect("b", trace_id="t2"))

    tracker.rollback("t1")
    assert tracker.audit("t1") == []
    assert tracker.audit("t2") == [tracker.replay(kept)]


def test_irreversible_effect_is_cleared_without_undo() -> None:
    tracker = EffectTracker()
    applied: list[str] = []
    tracker.record(_effect("proc", trace_id="t", undo=_recorder(applied, "proc"), reversible=False))

    report = tracker.rollback("t")
    assert report.reverted == []
    assert report.undo_failed == []
    assert applied == []  # 不可逆：不撤销
    assert tracker.audit("t") == []  # 随清账出账


def test_effect_tracker_undo_failed_stays_in_ledger() -> None:
    tracker = EffectTracker()

    def failing_undo() -> None:
        raise RuntimeError

    failed = tracker.record(_effect("x", trace_id="t", undo=failing_undo))
    ok = tracker.record(_effect("y", trace_id="t"))

    report = tracker.rollback("t")
    assert report.undo_failed == [failed]
    assert report.reverted == [ok]
    assert [e.target for e in tracker.audit("t")] == ["x"]  # 失败者留账隔离


def test_clear_removes_ledger_without_undo() -> None:
    tracker = EffectTracker()
    applied: list[str] = []
    tracker.record(_effect("a", trace_id="t1", undo=_recorder(applied, "a")))
    tracker.record(_effect("b", trace_id="t2", undo=_recorder(applied, "b")))

    tracker.clear("t1")
    assert applied == []  # 清账不触发 undo
    assert tracker.audit("t1") == []
    assert tracker.audit("t2") != []

    tracker.clear()
    assert applied == []
    assert tracker.audit("t2") == []


def test_coeffect_resolve_missing() -> None:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    with pytest.raises(CoeffectMissing) as exc_info:
        resolver.resolve(["filesystem:read", "network:outbound"])
    assert "network:outbound" in exc_info.value.required


def test_secret_handle_not_leaked() -> None:
    resolver = CoeffectResolver()
    resolver.register("secret:llm_api_key", "sk-RAW-SECRET-123", secret=True)
    ctx = resolver.resolve(["secret:llm_api_key"])
    handle = ctx.get("secret:llm_api_key")
    assert isinstance(handle, SecretRef)
    assert "sk-RAW-SECRET-123" not in repr(handle)
    assert resolver.resolve_secret("secret:llm_api_key") == "sk-RAW-SECRET-123"
