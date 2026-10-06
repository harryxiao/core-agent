"""Bundle 打包 / 解包（composition）。

把插件引用打包为跨部署可复用的 bundle（携带内容哈希），解包时校验哈希，
不符拒绝引入，避免脏分发。制品清单（`load_manifest`）为发布入口的内容载体：
哈希一律由**制品内容**派生，SHALL NOT 退化为以版本名等元信息充当内容哈希。

对应接口：doc/03-interfaces/composition-interface.md §1
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from .errors import CompositionError, CompositionErrorCode
from .models import Bundle, PluginRef


def content_hash(plugin_refs: list[PluginRef]) -> str:
    """对插件引用内容做稳定哈希（跨部署一致）。"""
    canonical = "|".join(f"{ref.plugin_id}@{ref.generation}" for ref in plugin_refs)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _refs_from_manifest(payload: object, location: str) -> list[PluginRef]:
    """清单 `plugin_refs` → `PluginRef` 列表；非法（非对象 / 非列表 / 缺字段）⇒ BUNDLE_INVALID。"""
    if not isinstance(payload, dict):
        raise CompositionError(
            CompositionErrorCode.BUNDLE_INVALID,
            f"bundle 制品清单非法（须为 JSON 对象）: {location}",
        )
    raw = cast("dict[str, Any]", payload).get("plugin_refs")
    if not isinstance(raw, list):
        raise CompositionError(
            CompositionErrorCode.BUNDLE_INVALID,
            f"bundle 制品清单非法（plugin_refs 须为列表）: {location}",
        )
    try:
        return [
            PluginRef(str(item["plugin_id"]), int(item["generation"]))
            for item in cast("list[Any]", raw)
        ]
    except (TypeError, KeyError, ValueError) as exc:
        raise CompositionError(
            CompositionErrorCode.BUNDLE_INVALID,
            f"bundle 制品清单非法（引用项须含 plugin_id / generation）: {location}",
        ) from exc


def _manifest_name(payload: object, path: Path) -> str:
    """清单声明的 bundle 名；未声明 ⇒ 取清单文件名的 stem（元信息不参与哈希）。"""
    declared = cast("dict[str, Any]", payload).get("name") if isinstance(payload, dict) else None
    return str(declared) if declared else path.stem


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

    def load_manifest(self, location: str) -> Bundle:
        """读 bundle 制品清单（JSON）→ Bundle（哈希由**制品内容**派生，非元信息）。

        清单声明 ``plugin_refs``（``plugin_id`` / ``generation``）与可选 ``name``
        （缺省取清单文件名的 stem）；内容哈希复用 ``content_hash`` 单一真源。
        清单不可读 / 非法 ⇒ ``BUNDLE_INVALID``（composition spec「bundle 分发格式」/
        账本 E84-a —— SHALL NOT 退化为以元信息充当内容哈希）。
        """
        path = Path(location)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CompositionError(
                CompositionErrorCode.BUNDLE_INVALID,
                f"bundle 制品清单不可读: {location}（{exc}）",
            ) from exc
        return self.pack(_refs_from_manifest(payload, location), name=_manifest_name(payload, path))

    def unpack(self, bundle: Bundle) -> list[PluginRef]:
        """解包 bundle，校验内容哈希；不符抛 BUNDLE_INVALID。"""
        if content_hash(bundle.plugin_refs) != bundle.hash:
            raise CompositionError(
                CompositionErrorCode.BUNDLE_INVALID,
                f"bundle {bundle.name}@{bundle.version} 哈希不符",
            )
        return list(bundle.plugin_refs)
