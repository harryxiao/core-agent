"""plugin-registry 安装抽象单元测试（M1）。

覆盖 spec/plugin-registry「插件来源与安装」场景：
- 三 kind（skill/mcp/cli）discover→install→uninstall 闭环
- 签名校验失败拒绝（SIGNATURE_INVALID）/ 来源不可达（SOURCE_NOT_FOUND）/ 安装失败（INSTALL_FAILED）
- 依赖环拒绝（复用 registry CIRCULAR_DEPENDENCY）
"""

from __future__ import annotations

import pytest

from core.plugin_registry import (
    DomainError,
    ErrorCode,
    InstallableAsset,
    PluginInstaller,
    PluginKind,
    PluginRegistry,
    PluginSource,
)


class _FakePlugin:
    """满足 Plugin 结构契约的最小测试插件。"""

    def __init__(self, plugin_id: str, deps: list[str] | None = None) -> None:
        self.plugin_id = plugin_id
        self.generation = 0
        self.schema: dict = {"type": "object"}
        self.coeffects: list[str] = []
        self.deps = deps or []
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def unload(self) -> None:
        self.loaded = False

    def check(self) -> bool:
        return True


def _resolver():
    return lambda source, location: {"name": location}


def test_three_kinds_install_uninstall_closure() -> None:
    for kind in (PluginKind.SKILL, PluginKind.MCP, PluginKind.CLI):
        registry = PluginRegistry()
        installer = PluginInstaller(registry=registry, source_resolver=_resolver())
        asset = installer.discover(PluginSource.LOCAL_PATH, "pkg", kind)
        assert asset.kind is kind
        assert asset.source is PluginSource.LOCAL_PATH
        installer.verify(asset, "sig")
        installer.install(asset)
        plugin_id = f"test.{kind.value}"
        installer.register(asset, _FakePlugin(plugin_id))
        installer.activate(plugin_id)
        installer.deactivate(plugin_id)
        installer.uninstall(plugin_id)
        assert registry.list_ids() == []  # 卸载释放，无悬空


def test_source_not_found() -> None:
    installer = PluginInstaller()  # 默认 resolver 未接入 → SOURCE_NOT_FOUND
    with pytest.raises(DomainError) as exc_info:
        installer.discover(PluginSource.LOCAL_PATH, "missing", PluginKind.SKILL)
    assert exc_info.value.code is ErrorCode.SOURCE_NOT_FOUND


def test_signature_invalid() -> None:
    installer = PluginInstaller(
        source_resolver=_resolver(), verifier=lambda asset, sig: bool(sig == "valid")
    )
    asset = installer.discover(PluginSource.GIT_REPO, "repo", PluginKind.SKILL)
    with pytest.raises(DomainError) as exc_info:
        installer.verify(asset, "bad")
    assert exc_info.value.code is ErrorCode.SIGNATURE_INVALID


def test_install_failed() -> None:
    def failing_installer(asset) -> None:
        raise RuntimeError("boom")

    installer = PluginInstaller(source_resolver=_resolver(), installer=failing_installer)
    asset = installer.discover(PluginSource.LOCAL_PATH, "pkg", PluginKind.SKILL)
    with pytest.raises(DomainError) as exc_info:
        installer.install(asset)
    assert exc_info.value.code is ErrorCode.INSTALL_FAILED


def test_dependency_cycle_rejected_on_register() -> None:
    installer = PluginInstaller(source_resolver=_resolver())
    asset = installer.discover(PluginSource.LOCAL_PATH, "pkg", PluginKind.SKILL)
    installer.register(asset, _FakePlugin("a", deps=["b"]))
    with pytest.raises(DomainError) as exc_info:
        installer.register(asset, _FakePlugin("b", deps=["a"]))
    assert exc_info.value.code is ErrorCode.CIRCULAR_DEPENDENCY


def test_uninstall_calls_symmetric_uninstaller() -> None:
    """uninstall 调用对称 uninstaller 钩子回退真实注册（不再只清账本）。"""
    called: list[InstallableAsset] = []

    def fake_uninstall(asset: InstallableAsset) -> None:
        called.append(asset)

    installer = PluginInstaller(source_resolver=_resolver(), uninstaller=fake_uninstall)
    asset = installer.discover(PluginSource.LOCAL_PATH, "pkg", PluginKind.SKILL)
    installer.register(asset, _FakePlugin("a"))
    installer.uninstall("a")
    assert called == [asset]
    assert installer.installed() == []
