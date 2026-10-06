"""组合引擎（composition）—— 门面编排。

组合 resolver + packager + distributor，对外暴露 resolve / revert / pack / unpack /
publish / fetch。静态组合代数：无业务逻辑、永不进化，只消费插件引用。

对应接口：doc/03-interfaces/composition-interface.md §3/§4
"""

from __future__ import annotations

from typing import Any

from .distributor import BundleDistributor
from .models import Bundle, PluginRef, Profile, ResolvedSet
from .packager import BundlePackager
from .resolver import ProfileResolver


class CompositionEngine:
    """组合引擎：门面，组合 resolver/packager/distributor。"""

    plugin_id = "composition.engine"
    generation = 1
    schema: dict[str, Any] = {"type": "object"}
    coeffects: list[str] = []

    def __init__(
        self,
        *,
        profiles: dict[str, Profile] | None = None,
        bundles: dict[str, Bundle] | None = None,
        packager: BundlePackager | None = None,
        distributor: BundleDistributor | None = None,
    ) -> None:
        self._packager = packager if packager is not None else BundlePackager()
        self._distributor = (
            distributor if distributor is not None else BundleDistributor(self._packager)
        )
        self._resolver = ProfileResolver(
            profiles=profiles,
            bundles=bundles,
            packager=self._packager,
        )

    def load(self) -> None:
        """无状态资源，no-op。"""

    def unload(self) -> None:
        """无状态资源，no-op。"""

    def check(self) -> bool:
        """自检：packager 打包 / 解包可往返。"""
        return self._packager.check()

    def resolve(self, profile: str) -> ResolvedSet:
        """按 profile 名解析最终插件集。"""
        return self._resolver.resolve(profile)

    def revert(self, resolved: ResolvedSet) -> ResolvedSet:
        """移除 patch 覆盖，回退至覆盖前分层结果（幂等，返回新结果）。"""
        return self._resolver.revert(resolved)

    def pack(self, plugins: list[PluginRef]) -> Bundle:
        """打包插件引用为 bundle。"""
        return self._packager.pack(plugins)

    def unpack(self, bundle: Bundle) -> list[PluginRef]:
        """解包 bundle（校验哈希）。"""
        return self._packager.unpack(bundle)

    def publish(self, bundle: Bundle, registry: dict[str, Bundle] | None = None) -> str:
        """发布 bundle，返回可寻址引用。"""
        return self._distributor.publish(bundle, registry)

    def fetch(self, name: str, version: str = "latest") -> Bundle:
        """按名/版本拉取 bundle。"""
        return self._distributor.fetch(name, version)
