"""组合与分发层（L5 Composition）。

CORE-Harness 唯一的静态层：只有组合代数、没有业务逻辑、永不进化。
通过 profile（命名组合）/ bundle（分发格式）/ patch.yml（用户覆盖）三要素，
把已结晶的技能与插件按需组合、跨部署分发、按用户差异覆盖。

层叠解析顺序固定为「bundle 层叠 → patch.yml 覆盖」，同名项由 patch.yml 覆盖；
所有组合 / 覆盖操作可逆、可回退。对应规格 `openspec/specs/composition/spec.md`。
"""

from .distributor import BundleDistributor
from .engine import CompositionEngine
from .errors import CompositionError, CompositionErrorCode
from .models import Bundle, PatchSpec, PluginRef, Profile, ResolvedSet
from .packager import BundlePackager
from .resolver import ProfileResolver

__all__ = [
    "Bundle",
    "BundleDistributor",
    "BundlePackager",
    "CompositionEngine",
    "CompositionError",
    "CompositionErrorCode",
    "PatchSpec",
    "PluginRef",
    "Profile",
    "ProfileResolver",
    "ResolvedSet",
]
