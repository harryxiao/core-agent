"""Profile 解析器（composition）。

按 profile 名解析最终插件集：load_profile → unpack bundles → layer（后层覆盖前层）
→ apply_patch（显式 patch 优先）。层叠顺序确定，解析结果可逆、可回退。

对应接口：doc/03-interfaces/composition-interface.md §1/§3
"""

from __future__ import annotations

from typing import Any

from .errors import CompositionError, CompositionErrorCode
from .models import Bundle, PatchSpec, PluginRef, Profile, ResolvedSet
from .packager import BundlePackager


def detect_cycle(bundles: dict[str, Bundle]) -> list[str] | None:
    """检测 bundle 依赖图中的环；返回环路径（无环返回 None）。"""
    _white, _gray, _black = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(name: str) -> list[str] | None:
        color[name] = _gray
        stack.append(name)
        bundle = bundles.get(name)
        deps = bundle.deps if bundle is not None else []
        for dep in deps:
            state = color.get(dep, _white)
            if state == _gray:
                return [*stack[stack.index(dep) :], dep]
            found = visit(dep) if state == _white else None
            if found is not None:
                return found
        stack.pop()
        color[name] = _black
        return None

    for name in bundles:
        if color.get(name, _white) == _white:
            found = visit(name)
            if found is not None:
                return found
    return None


class ProfileResolver:
    """按 profile 名解析最终插件集（层叠 + 覆盖）。"""

    plugin_id = "composition.resolver"
    generation = 1
    schema: dict[str, Any] = {"type": "object"}
    coeffects: list[str] = []

    def __init__(
        self,
        *,
        profiles: dict[str, Profile] | None = None,
        bundles: dict[str, Bundle] | None = None,
        packager: BundlePackager | None = None,
    ) -> None:
        self._profiles: dict[str, Profile] = profiles if profiles is not None else {}
        self._bundles: dict[str, Bundle] = bundles if bundles is not None else {}
        self._packager = packager if packager is not None else BundlePackager()

    def load(self) -> None:
        """无状态资源，no-op。"""

    def unload(self) -> None:
        """无状态资源，no-op。"""

    def check(self) -> bool:
        """自检：所有 profile 引用的 bundle 均存在且无依赖环。"""
        if detect_cycle(self._bundles) is not None:
            return False
        return all(
            name in self._bundles for profile in self._profiles.values() for name in profile.bundles
        )

    def load_profile(self, profile: str) -> Profile:
        """按名加载 profile；不存在抛 PLUGIN_MISSING。"""
        resolved = self._profiles.get(profile)
        if resolved is None:
            raise CompositionError(CompositionErrorCode.PLUGIN_MISSING, f"profile {profile} 不存在")
        return resolved

    def resolve(self, profile: str) -> ResolvedSet:
        """解析最终插件集：load_profile → unpack bundles → layer → apply_patch。"""
        current = self.load_profile(profile)
        cycle = detect_cycle(self._bundles)
        if cycle is not None:
            raise CompositionError(
                CompositionErrorCode.CIRCULAR_DEPENDENCY,
                " → ".join(cycle),
            )
        layered: list[list[PluginRef]] = []
        for name in current.bundles:
            bundle = self._bundles.get(name)
            if bundle is None:
                raise CompositionError(
                    CompositionErrorCode.PLUGIN_MISSING,
                    f"profile {profile} 引用不存在的 bundle {name}",
                )
            layered.append(self._packager.unpack(bundle))
        merged = self.layer(layered)
        final = self.apply_patch(merged, current.patch)
        return ResolvedSet(
            profile=profile,
            plugins=final,
            layered=list(merged),  # 覆盖前分层结果：`revert` 的恢复目标（规格「层叠解析」）
            overrides=dict(current.patch.overrides),
        )

    @staticmethod
    def revert(resolved: ResolvedSet) -> ResolvedSet:
        """移除 patch 覆盖，回退至**覆盖前**分层结果（规格「层叠解析」可回退）。

        返回**新** `ResolvedSet`（不改实参）：`plugins` 取覆盖前分层结果、`overrides` 清空、
        `layered` 原样携带 ⇒ 对回退结果再回退**结果不变**（幂等）。
        """
        return ResolvedSet(
            profile=resolved.profile,
            plugins=list(resolved.layered),
            layered=list(resolved.layered),
            overrides={},
        )

    @staticmethod
    def layer(bundle_lists: list[list[PluginRef]]) -> list[PluginRef]:
        """bundle 层叠：按顺序合并，同名 plugin_id 后层覆盖前层。"""
        merged: dict[str, PluginRef] = {}
        for refs in bundle_lists:
            for ref in refs:
                merged[ref.plugin_id] = ref
        return list(merged.values())

    @staticmethod
    def apply_patch(plugins: list[PluginRef], patch: PatchSpec) -> list[PluginRef]:
        """patch.yml 覆盖：显式 patch 优先；目标不存在或值类型不支持则报冲突。"""
        by_id = {ref.plugin_id: ref for ref in plugins}
        for plugin_id, override in sorted(patch.overrides.items()):
            if plugin_id not in by_id:
                raise CompositionError(
                    CompositionErrorCode.PATCH_CONFLICT,
                    f"patch 覆盖 {plugin_id} 不在层叠结果中",
                )
            # bool 是 int 子类：YAML `true`/`false` 不得静默落为 generation 1/0（账本 E70）
            if not isinstance(override, int) or isinstance(override, bool):
                raise CompositionError(
                    CompositionErrorCode.PATCH_CONFLICT,
                    f"patch 覆盖 {plugin_id} 值类型不支持（需 generation 整数，布尔除外）",
                )
            by_id[plugin_id] = PluginRef(plugin_id, override)
        return list(by_id.values())
