"""Bundle 分发（composition）。

发布 bundle 到插件仓库（可寻址引用），按名/版本拉取，校验哈希后返回。

对应接口：doc/03-interfaces/composition-interface.md §4
"""

from __future__ import annotations

from .errors import CompositionError, CompositionErrorCode
from .models import Bundle
from .packager import BundlePackager


class BundleDistributor:
    """发布 / 拉取 bundle，按名寻址，校验哈希。"""

    def __init__(self, packager: BundlePackager | None = None) -> None:
        self._packager = packager if packager is not None else BundlePackager()
        self._registry: dict[str, Bundle] = {}

    def publish(self, bundle: Bundle, registry: dict[str, Bundle] | None = None) -> str:
        """发布 bundle 到插件仓库，返回可寻址引用（name@version）。"""
        store = self._registry if registry is None else registry
        store[bundle.name] = bundle
        return f"{bundle.name}@{bundle.version}"

    def fetch(self, name: str, version: str = "latest") -> Bundle:
        """按名/版本拉取 bundle，校验哈希；缺失/版本不符/哈希不符抛 BUNDLE_INVALID。"""
        bundle = self._registry.get(name)
        if bundle is None:
            raise CompositionError(CompositionErrorCode.BUNDLE_INVALID, f"bundle {name} 不存在")
        if version not in ("latest", bundle.version):
            raise CompositionError(
                CompositionErrorCode.BUNDLE_INVALID,
                f"bundle {name} 版本 {version} 不存在（当前 {bundle.version}）",
            )
        self._packager.unpack(bundle)  # 校验哈希，不符抛 BUNDLE_INVALID
        return bundle
