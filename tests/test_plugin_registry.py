"""plugin-registry 单元测试（对齐规格场景 + M0 验收）。

覆盖 spec/plugin-registry 的场景：
- 注册并校验 / 卸载干净 / 并发热插拔原子性 / 注册超时
- 依赖满足 / 循环依赖检测
- 能力边界 / 插件崩溃隔离
以及 EffectTracker / CoeffectResolver 的可逆效应与密钥句柄语义。
"""

from __future__ import annotations

import time
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

    def __init__(  # noqa: PLR0913 — 测试桩，参数皆为可选的注入行为
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
    report = tracker.rollback("t1")
    assert applied == ["b", "a"]  # 逆序撤销
    assert set(report.reverted) == {e1, e2}
    assert tracker.audit("t1") == [tracker.replay(e1), tracker.replay(e2)]


def test_effect_tracker_undo_failed() -> None:
    tracker = EffectTracker()

    def failing_undo() -> None:
        raise RuntimeError

    tracker.record(
        Effect(
            op="file_write",
            target="x",
            undo=failing_undo,
            reversible=True,
            coeffect=[],
            trace_id="t",
            ts=1.0,
        )
    )
    report = tracker.rollback("t")
    assert report.undo_failed != []


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
