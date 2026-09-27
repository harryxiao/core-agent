"""Bundle 打包 / 解包（composition）。

把插件引用打包为跨部署可复用的 bundle（携带内容哈希），解包时校验哈希，
不符拒绝引入，避免脏分发。

对应接口：doc/03-interfaces/composition-interface.md §1
"""

from __future__ import annotations

import hashlib
from typing import Any

from .errors import CompositionError, CompositionErrorCode
from .models import Bundle, PluginRef


def content_hash(plugin_refs: list[PluginRef]) -> str:
    """对插件引用内容做稳定哈希（跨部署一致）。"""
    canonical = "|".join(f"{ref.plugin_id}@{ref.generation}" for ref in plugin_refs)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class BundlePackager:
    """打包 / 解包 bundle，校验内容哈希。"""

    plugin_id = "composition.packager"
    generation = 1
    schema: dict[str, Any] = {"type": "object"}
    coeffects: list[str] = []

    def load(self) -> None:
        """无状态资源，no-op。"""

    def unload(self) -> None:
        """无状态资源，no-op。"""

    def check(self) -> bool:
        """自检：打包 / 解包可往返。"""
        refs = [PluginRef("composition.self-check", 1)]
        return self.unpack(self.pack(refs)) == refs

    def pack(self, plugins: list[PluginRef], *, name: str = "") -> Bundle:
        """把一组插件引用打包为 bundle（计算内容哈希）。"""
        return Bundle(
            name=name,
            version="1.0.0",
            hash=content_hash(plugins),
            plugin_refs=list(plugins),
        )

    def unpack(self, bundle: Bundle) -> list[PluginRef]:
        """解包 bundle，校验内容哈希；不符抛 BUNDLE_INVALID。"""
        if content_hash(bundle.plugin_refs) != bundle.hash:
            raise CompositionError(
                CompositionErrorCode.BUNDLE_INVALID,
                f"bundle {bundle.name}@{bundle.version} 哈希不符",
            )
        return list(bundle.plugin_refs)
