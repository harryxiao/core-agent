"""组合与分发层数据模型（composition）。

承载三要素组合数据流：PluginRef（插件轻量引用）→ Profile（命名组合）→
Bundle（分发格式）→ PatchSpec（用户覆盖）→ ResolvedSet（层叠 + 覆盖结果）。

对应接口：doc/03-interfaces/composition-interface.md §2
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PluginRef:
    """插件轻量引用：指向插件仓库中某代插件，只消费、不改造实现。"""

    plugin_id: str
    generation: int


@dataclass
class PatchSpec:
    """用户覆盖：plugin_id -> 覆盖值（generation），不改 profile/bundle。"""

    overrides: dict[str, object] = field(default_factory=dict[str, object])


@dataclass
class Profile:
    """命名组合：一个命名指向一个可复用插件组合集合。"""

    name: str
    bundles: list[str] = field(default_factory=list[str])  # 层叠顺序即列表顺序
    patch: PatchSpec = field(default_factory=PatchSpec)


@dataclass
class Bundle:
    """分发格式：已结晶插件打包，跨部署复用，携带哈希保证一致。"""

    name: str
    version: str
    hash: str
    plugin_refs: list[PluginRef] = field(default_factory=list[PluginRef])
    deps: list[str] = field(default_factory=list[str])  # 依赖的 bundle 名（循环依赖检测）


@dataclass
class ResolvedSet:
    """层叠 + 覆盖后的最终插件集（覆盖项可回退到覆盖前状态）。"""

    profile: str
    plugins: list[PluginRef]
    overrides: dict[str, object] = field(default_factory=dict[str, object])
