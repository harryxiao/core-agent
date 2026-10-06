"""composition 单元测试（对齐契约红线：层叠顺序确定 / 循环依赖拦截 / patch 覆盖冲突兜底）。"""

from __future__ import annotations

import json

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
    ResolvedSet,
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


# ---- 制品清单 → 内容哈希（change 0143 / 账本 E84-a）----


def _manifest(tmp_path, name: str, refs: list[tuple[str, int]]) -> str:
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "name": name,
                "plugin_refs": [{"plugin_id": pid, "generation": gen} for pid, gen in refs],
            }
        ),
        encoding="utf-8",
    )
    return str(path)


def test_load_manifest_hash_derives_from_content_not_meta(tmp_path) -> None:
    """同内容异元信息（清单名 + bundle 名皆不同）⇒ **同哈希**（哈希由制品内容派生）。"""
    packager = BundlePackager()
    left = packager.load_manifest(_manifest(tmp_path, "release-a", [("a", 1), ("b", 2)]))
    right = packager.load_manifest(_manifest(tmp_path, "release-b", [("a", 1), ("b", 2)]))
    assert left.name != right.name, "元信息确实不同"
    assert left.hash == right.hash, "内容相同 ⇒ 哈希相同"
    assert left.hash == packager.pack(_refs(("a", 1), ("b", 2))).hash, "与真口径 pack 同源"


def test_load_manifest_hash_changes_with_content(tmp_path) -> None:
    """改动任一 ``generation`` ⇒ 哈希随之改变（异内容 ⇒ 异哈希）。"""
    packager = BundlePackager()
    before = packager.load_manifest(_manifest(tmp_path, "same-name", [("a", 1)]))
    after = packager.load_manifest(_manifest(tmp_path, "same-name", [("a", 2)]))
    assert before.hash != after.hash


def test_load_manifest_order_is_significant(tmp_path) -> None:
    """规范形为**有序**拼接：内容项相同而次序不同 ⇒ 哈希不同（不静默排序）。"""
    packager = BundlePackager()
    left = packager.load_manifest(_manifest(tmp_path, "left", [("a", 1), ("b", 2)]))
    right = packager.load_manifest(_manifest(tmp_path, "right", [("b", 2), ("a", 1)]))
    assert left.hash != right.hash


def test_load_manifest_name_defaults_to_file_stem(tmp_path) -> None:
    """清单未声明 ``name`` ⇒ 取清单文件名的 stem（元信息不参与哈希，故不影响口径）。"""
    path = tmp_path / "fallback-name.json"
    path.write_text(
        json.dumps({"plugin_refs": [{"plugin_id": "a", "generation": 1}]}), encoding="utf-8"
    )
    assert BundlePackager().load_manifest(str(path)).name == "fallback-name"


@pytest.mark.parametrize(
    "payload",
    [
        None,  # 清单缺失（路径不存在）
        "{ not json",  # 非法 JSON
        json.dumps([{"plugin_id": "a", "generation": 1}]),  # 顶层非对象
        json.dumps({"plugin_refs": "a@1"}),  # plugin_refs 非列表
        json.dumps({"plugin_refs": [{"plugin_id": "a"}]}),  # 引用项缺 generation
        json.dumps({"plugin_refs": [{"generation": 1}]}),  # 引用项缺 plugin_id
    ],
)
def test_load_manifest_invalid_rejected(tmp_path, payload: str | None) -> None:
    """清单缺失 / 非法 ⇒ ``BUNDLE_INVALID``（SHALL NOT 退化为元信息哈希）。"""
    path = tmp_path / "broken.json"
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    with pytest.raises(CompositionError) as exc_info:
        BundlePackager().load_manifest(str(path))
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


# ---- 覆盖可回退（change 0136 / 账本 E75）----


def _patched() -> tuple[ProfileResolver, ResolvedSet]:
    """构造「层叠 a=1,b=1 且 patch 覆盖 b=9」的解析场景。"""
    bundles = {"core": _bundle("core", _refs(("a", 1), ("b", 1)))}
    profile = Profile(name="web", bundles=["core"], patch=PatchSpec({"b": 9}))
    resolver = ProfileResolver(profiles={"web": profile}, bundles=bundles)
    return resolver, resolver.resolve("web")


def test_revert_restores_pre_patch_layering() -> None:
    """回退移除 patch 覆盖 ⇒ 回到覆盖前分层结果、覆盖项清空；实参不被就地修改（change 0136）。"""
    resolver, resolved = _patched()
    assert {ref.plugin_id: ref.generation for ref in resolved.layered} == {"a": 1, "b": 1}

    reverted = resolver.revert(resolved)

    assert {ref.plugin_id: ref.generation for ref in reverted.plugins} == {"a": 1, "b": 1}
    assert reverted.overrides == {}
    # 纯函数语义：原结果保持覆盖后状态
    assert {ref.plugin_id: ref.generation for ref in resolved.plugins} == {"a": 1, "b": 9}


def test_revert_is_idempotent() -> None:
    """对回退结果再回退，结果不变（幂等）。"""
    resolver, resolved = _patched()
    once = resolver.revert(resolved)
    assert resolver.revert(once) == once


def test_revert_without_patch_is_noop() -> None:
    """无 patch 的 profile：回退等价于原结果（分层即终态）。"""
    bundles = {"core": _bundle("core", _refs(("a", 1)))}
    profile = Profile(name="web", bundles=["core"])
    resolver = ProfileResolver(profiles={"web": profile}, bundles=bundles)

    resolved = resolver.resolve("web")

    assert resolved.overrides == {}
    assert resolver.revert(resolved).plugins == resolved.plugins


def test_engine_facade_exposes_revert() -> None:
    """门面透出 revert（调用方不必直达 resolver）。"""
    bundles = {"core": _bundle("core", _refs(("a", 1), ("b", 1)))}
    profile = Profile(name="web", bundles=["core"], patch=PatchSpec({"b": 9}))
    engine = CompositionEngine(profiles={"web": profile}, bundles=bundles)

    resolved = engine.resolve("web")

    assert {ref.plugin_id: ref.generation for ref in engine.revert(resolved).plugins} == {
        "a": 1,
        "b": 1,
    }


def test_patch_override_bool_rejected() -> None:
    """bool 虽为 int 子类，SHALL 按 PATCH_CONFLICT 拒绝，不静默落为 generation 1（E70）。"""
    bundles = {"core": _bundle("core", _refs(("a", 1)))}
    profile = Profile(name="web", bundles=["core"], patch=PatchSpec({"a": True}))
    resolver = ProfileResolver(profiles={"web": profile}, bundles=bundles)
    with pytest.raises(CompositionError) as exc_info:
        resolver.resolve("web")
    assert exc_info.value.code is CompositionErrorCode.PATCH_CONFLICT
