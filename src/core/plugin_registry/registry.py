"""插件注册表（PluginRegistry / L0 组合基底）。

提供「插件即原子」的组合代数：注册 / 加载 / 卸载 / 自检 / 组合激活，
并负责依赖解析（含循环依赖检测）、崩溃隔离（插件异常不拖垮宿主）、
并发热插拔原子性。所有可变操作经 ``threading.RLock`` 串行化，状态迁移
原子完成，不出现半注册 / 半卸载的中间态。

对应规格：doc/openspec/specs/plugin-registry/spec.md
模块设计：doc/02-modules/plugin-registry.md
"""

from __future__ import annotations

import threading
from enum import StrEnum
from typing import Any, cast

from .errors import DomainError, ErrorCode
from .plugin import Plugin


class PluginState(StrEnum):
    """插件生命周期状态。"""

    REGISTERED = "registered"
    LOADED = "loaded"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    UNLOADED = "unloaded"
    ARCHIVED = "archived"
    FAULTED = "faulted"  # 崩溃隔离：插件运行时异常被标记故障，不拖垮宿主


class PluginRegistry:
    """插件注册表：管理插件的注册、生命周期与依赖解析。"""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._generations: dict[str, int] = {}
        self._states: dict[str, PluginState] = {}
        self._deps: dict[str, list[str]] = {}
        self._lock = threading.RLock()

    # ---- 注册与校验 ----

    def register(self, plugin: Plugin) -> None:
        """校验 manifest 并登记插件，状态置为 ``registered``。"""
        self._validate_manifest(plugin)
        deps = list(getattr(plugin, "deps", None) or [])
        self._validate_deps(deps)
        with self._lock:
            existing = self._generations.get(plugin.plugin_id)
            if existing is not None and plugin.generation < existing:
                raise DomainError(
                    ErrorCode.GENERATION_CONFLICT,
                    f"插件 {plugin.plugin_id} 世代冲突：{plugin.generation} < 现有 {existing}",
                )
            self._check_cycle_locked(plugin.plugin_id, deps)
            self._plugins[plugin.plugin_id] = plugin
            self._generations[plugin.plugin_id] = plugin.generation
            self._deps[plugin.plugin_id] = deps
            self._states[plugin.plugin_id] = PluginState.REGISTERED

    def _validate_manifest(self, plugin: Any) -> None:
        # 运行期校验不可信输入：plugin 可能不满足 Protocol（鸭子类型），故按 Any 校验
        if not isinstance(plugin.plugin_id, str) or not plugin.plugin_id:
            raise DomainError(ErrorCode.INVALID_MANIFEST, "plugin_id 必须为非空字符串")
        if not isinstance(plugin.generation, int) or plugin.generation < 0:
            raise DomainError(ErrorCode.INVALID_MANIFEST, "generation 必须为 >=0 的整数")
        if not isinstance(plugin.schema, dict):
            raise DomainError(ErrorCode.INVALID_SCHEMA, "schema 必须为 dict")
        coeffects: Any = plugin.coeffects
        if not isinstance(coeffects, list):
            raise DomainError(ErrorCode.INVALID_MANIFEST, "coeffects 必须为 list[str]")
        if not all(isinstance(c, str) for c in cast(list[object], coeffects)):
            raise DomainError(ErrorCode.INVALID_MANIFEST, "coeffects 必须为 list[str]")

    def _validate_deps(self, deps: Any) -> None:
        if not all(isinstance(d, str) for d in deps):
            raise DomainError(ErrorCode.INVALID_MANIFEST, "deps 必须为 list[str]")

    def _check_cycle_locked(self, new_id: str, deps: list[str]) -> None:
        graph = {**self._deps, new_id: deps}
        visiting: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            visiting.add(node)
            for dep in graph.get(node, []):
                if dep in graph and visit(dep):
                    return True
            visiting.remove(node)
            return False

        if visit(new_id):
            raise DomainError(ErrorCode.CIRCULAR_DEPENDENCY, f"循环依赖：{new_id}")

    # ---- 生命周期 ----

    def load(self, plugin_id: str, *, timeout: float | None = None) -> None:
        """加载插件（先加载依赖，再加载自身），状态置为 ``loaded``。"""
        with self._lock:
            plugin = self._require(plugin_id)
            state = self._states[plugin_id]
        if state in (PluginState.LOADED, PluginState.ACTIVE):
            return
        for dep in self._deps.get(plugin_id, []):
            self.load(dep, timeout=timeout)
        if timeout is None:
            self._load_inline(plugin_id, plugin)
        else:
            self._load_with_timeout(plugin_id, plugin, timeout)

    def _load_inline(self, plugin_id: str, plugin: Plugin) -> None:
        try:
            plugin.load()
        except Exception as exc:  # noqa: BLE001 — 崩溃隔离：异常不污染宿主
            with self._lock:
                self._states[plugin_id] = PluginState.FAULTED
            raise DomainError(
                ErrorCode.NOT_ACTIVE, f"插件 {plugin_id} load 崩溃，已隔离: {exc}"
            ) from exc
        with self._lock:
            self._states[plugin_id] = PluginState.LOADED

    def _load_with_timeout(self, plugin_id: str, plugin: Plugin, timeout: float) -> None:
        outcome: list[Exception | None] = [None]

        def _run() -> None:
            try:
                plugin.load()
            except Exception as exc:  # noqa: BLE001
                outcome[0] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout)
        with self._lock:
            if thread.is_alive():
                self._states[plugin_id] = PluginState.FAULTED
                raise DomainError(
                    ErrorCode.REGISTER_TIMEOUT, f"插件 {plugin_id} 注册超时（>{timeout}s）"
                )
            exc = outcome[0]
            if exc is not None:
                self._states[plugin_id] = PluginState.FAULTED
                raise DomainError(
                    ErrorCode.NOT_ACTIVE, f"插件 {plugin_id} load 崩溃，已隔离: {exc}"
                ) from exc
            self._states[plugin_id] = PluginState.LOADED

    def unload(self, plugin_id: str) -> None:
        """卸载插件（回收资源），状态置为 ``unloaded`` 并从注册表移除。"""
        with self._lock:
            plugin = self._require(plugin_id)
            if self._states[plugin_id] in (PluginState.UNLOADED, PluginState.ARCHIVED):
                return
        try:
            plugin.unload()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._states[plugin_id] = PluginState.FAULTED
            raise DomainError(ErrorCode.UNDO_FAILED, f"插件 {plugin_id} 卸载失败: {exc}") from exc
        with self._lock:
            self._plugins.pop(plugin_id, None)
            self._generations.pop(plugin_id, None)
            self._deps.pop(plugin_id, None)
            self._states.pop(plugin_id, None)

    def check(self, plugin_id: str) -> bool:
        """调用插件自检；异常时返回 False，不抛出。"""
        with self._lock:
            plugin = self._require(plugin_id)
        try:
            return plugin.check()
        except Exception:  # noqa: BLE001
            return False

    # ---- 激活 / 组合 ----

    def activate(self, plugin_id: str) -> None:
        """激活插件（loaded → active）。"""
        with self._lock:
            state = self._states.get(plugin_id)
            if state is None or state == PluginState.FAULTED:
                raise DomainError(ErrorCode.NOT_ACTIVE, f"插件不可激活: {plugin_id}")
            if state != PluginState.LOADED:
                raise DomainError(ErrorCode.NOT_ACTIVE, f"插件未加载，无法激活: {plugin_id}")
            self._states[plugin_id] = PluginState.ACTIVE

    def deactivate(self, plugin_id: str) -> None:
        """停用插件（active → loaded）。"""
        with self._lock:
            if self._states.get(plugin_id) != PluginState.ACTIVE:
                raise DomainError(ErrorCode.NOT_ACTIVE, f"插件未激活: {plugin_id}")
            self._states[plugin_id] = PluginState.LOADED

    def suspend(self, plugin_id: str) -> None:
        """暂停插件（active → suspended）。"""
        with self._lock:
            if self._states.get(plugin_id) != PluginState.ACTIVE:
                raise DomainError(ErrorCode.NOT_ACTIVE, f"插件未激活，无法暂停: {plugin_id}")
            self._states[plugin_id] = PluginState.SUSPENDED

    def resume(self, plugin_id: str) -> None:
        """恢复插件（suspended → active）。"""
        with self._lock:
            if self._states.get(plugin_id) != PluginState.SUSPENDED:
                raise DomainError(ErrorCode.NOT_ACTIVE, f"插件未暂停，无法恢复: {plugin_id}")
            self._states[plugin_id] = PluginState.ACTIVE

    def compose(self, plugin_ids: list[str]) -> None:
        """组合激活一组插件：先按依赖加载，再统一激活。"""
        for plugin_id in plugin_ids:
            self.load(plugin_id)
        for plugin_id in plugin_ids:
            self.activate(plugin_id)

    # ---- 查询 ----

    def get(self, plugin_id: str) -> Plugin | None:
        with self._lock:
            return self._plugins.get(plugin_id)

    def state(self, plugin_id: str) -> PluginState:
        with self._lock:
            return self._states.get(plugin_id, PluginState.UNLOADED)

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._plugins)

    def _require(self, plugin_id: str) -> Plugin:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise DomainError(ErrorCode.NOT_ACTIVE, f"插件未注册: {plugin_id}")
        return plugin
