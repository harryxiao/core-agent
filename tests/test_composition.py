"""composition 单元测试（对齐契约红线：层叠顺序确定 / 循环依赖拦截 / patch 覆盖冲突兜底）。"""

from __future__ import annotations

import pytest

from core.composition import (
    Bundle,
    BundlePackager,
    CompositionEngine,
    CompositionError,
    CompositionErrorCode,
    PatchSpec,
    PluginRef,
    Profile,
    ProfileResolver,
)


def _refs(*pairs: tuple[str, int]) -> list[PluginRef]:
    return [PluginRef(plugin_id, generation) for plugin_id, generation in pairs]


def _bundle(name: str, refs: list[PluginRef], *, deps: list[str] | None = None) -> Bundle:
    bundle = BundlePackager().pack(refs, name=name)
    if deps:
        bundle.deps = deps
    return bundle


# ---- 层叠解析顺序确定：后层覆盖前层 ----


def test_layer_later_overrides_earlier() -> None:
    refs = ProfileResolver.layer([_refs(("a", 1), ("b", 1)), _refs(("b", 2), ("c", 2))])
    by_id = {ref.plugin_id: ref.generation for ref in refs}
    assert by_id == {"a": 1, "b": 2, "c": 2}


def test_resolve_applies_bundle_then_patch() -> None:
    bundles = {"core": _bundle("core", _refs(("a", 1), ("b", 1)))}
    profile = Profile(name="web", bundles=["core"], patch=PatchSpec({"b": 9}))
    resolver = ProfileResolver(profiles={"web": profile}, bundles=bundles)
    result = resolver.resolve("web")
    by_id = {ref.plugin_id: ref.generation for ref in result.plugins}
    assert by_id == {"a": 1, "b": 9}
    assert result.overrides == {"b": 9}


# ---- 循环依赖拦截 ----


def test_circular_dependency_rejected() -> None:
    bundles = {
        "a": _bundle("a", _refs(("x", 1)), deps=["b"]),
        "b": _bundle("b", _refs(("y", 1)), deps=["a"]),
    }
    profile = Profile(name="web", bundles=["a"])
    resolver = ProfileResolver(profiles={"web": profile}, bundles=bundles)
    with pytest.raises(CompositionError) as exc_info:
        resolver.resolve("web")
    assert exc_info.value.code is CompositionErrorCode.CIRCULAR_DEPENDENCY


# ---- patch 覆盖冲突兜底 ----


def test_patch_conflict_on_unknown_plugin() -> None:
    bundles = {"core": _bundle("core", _refs(("a", 1)))}
    profile = Profile(name="web", bundles=["core"], patch=PatchSpec({"missing": 1}))
    resolver = ProfileResolver(profiles={"web": profile}, bundles=bundles)
    with pytest.raises(CompositionError) as exc_info:
        resolver.resolve("web")
    assert exc_info.value.code is CompositionErrorCode.PATCH_CONFLICT


# ---- profile 引用不存在 ----


def test_profile_missing_raises() -> None:
    with pytest.raises(CompositionError) as exc_info:
        ProfileResolver().resolve("nope")
    assert exc_info.value.code is CompositionErrorCode.PLUGIN_MISSING


def test_profile_missing_bundle_raises() -> None:
    profile = Profile(name="web", bundles=["ghost"])
    resolver = ProfileResolver(profiles={"web": profile}, bundles={})
    with pytest.raises(CompositionError) as exc_info:
        resolver.resolve("web")
    assert exc_info.value.code is CompositionErrorCode.PLUGIN_MISSING


# ---- bundle 校验失败 ----


def test_bundle_hash_mismatch_rejected() -> None:
    packager = BundlePackager()
    bundle = packager.pack(_refs(("a", 1)), name="core")
    tampered = Bundle(name="core", version="1.0.0", hash="deadbeef", plugin_refs=bundle.plugin_refs)
    with pytest.raises(CompositionError) as exc_info:
        packager.unpack(tampered)
    assert exc_info.value.code is CompositionErrorCode.BUNDLE_INVALID


# ---- 打包 / 解包 / 发布 / 拉取 往返 ----


def test_pack_unpack_roundtrip() -> None:
    packager = BundlePackager()
    refs = _refs(("a", 1), ("b", 2))
    assert packager.unpack(packager.pack(refs, name="core")) == refs


def test_publish_fetch_roundtrip() -> None:
    engine = CompositionEngine()
    bundle = engine.pack(_refs(("a", 1)))
    bundle.name = "skills"
    assert engine.publish(bundle) == "skills@1.0.0"
    assert engine.fetch("skills").plugin_refs == bundle.plugin_refs


def test_fetch_missing_bundle_raises() -> None:
    with pytest.raises(CompositionError) as exc_info:
        CompositionEngine().fetch("nope")
    assert exc_info.value.code is CompositionErrorCode.BUNDLE_INVALID
