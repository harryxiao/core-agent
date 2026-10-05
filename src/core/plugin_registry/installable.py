"""统一插件安装抽象（plugin-registry）。

把第三方插件（skill / mcp / cli）的安装生命周期收敛到 registry 层：
来源解析 discover → 签名校验 verify → 安装 install → 注册 register → 激活
activate → 停用 deactivate → 卸载 uninstall。

``InstallableAsset`` / ``PluginSource`` 为 M1/M2/M3 共享地基；签名校验 /
多源路由语义上提到此层复用（skillhub 语义上提，不合并执行实现，D3）。

对应规格：doc/openspec/specs/plugin-registry/spec.md「插件来源与安装」
接口：doc/03-interfaces/plugin-registry-interface.md §8
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, cast

from .errors import DomainError, ErrorCode
from .plugin import Plugin
from .registry import PluginRegistry, PluginState


class PluginSource(StrEnum):
    """插件来源四类。"""

    LOCAL_PATH = "local-path"
    GIT_REPO = "git-repo"
    MARKET_REGISTRY = "market-registry"
    MCP_ENDPOINT = "mcp-endpoint"


class PluginKind(StrEnum):
    """可安装插件类型。"""

    SKILL = "skill"
    MCP = "mcp"
    CLI = "cli"


@dataclass(frozen=True)
class InstallableAsset:
    """统一插件安装资产：类型 / 来源 / manifest / 生命周期阶段。"""

    kind: PluginKind
    source: PluginSource
    manifest: dict[str, Any] = field(default_factory=dict[str, Any])
    lifecycle: str = "discover"


SourceResolver = Callable[[PluginSource, str], dict[str, Any]]
SignatureVerifier = Callable[[InstallableAsset, str], bool]
Installer = Callable[[InstallableAsset], None]
Uninstaller = Callable[[InstallableAsset], None]


def _default_resolve(source: PluginSource, location: str) -> dict[str, Any]:
    """默认来源解析：真实多源拉取（读盘 / 克隆 / 市场 / MCP）依赖外部，离线未接入。"""
    raise DomainError(ErrorCode.SOURCE_NOT_FOUND, f"来源不可达（未接入 resolver）: {location}")


def _default_verify(asset: InstallableAsset, signature: str) -> bool:
    """默认签名校验：无签名要求时放行（严格校验由 skillhub 注入）。"""
    return True


def _default_install(asset: InstallableAsset) -> None:
    """默认安装：无副作用（真实物化由执行层按 kind 适配）。"""
    return None


def _default_uninstall(asset: InstallableAsset) -> None:
    """默认卸载：无副作用（真实物化回退由执行层按 kind 适配）。"""
    return None


class InstallStore(Protocol):
    """安装账本视图：:class:`PluginInstaller` 的持久化钩子（执行层 ``plugins.installs`` 实现）。

    本模块是 L0 组合基底，**不得** import 上层的 ``plugins`` 实现（依赖方向固定），
    故此处只声明结构（鸭子类型），由组合根注入具体实现。
    """

    def records(self) -> dict[str, InstallableAsset]:
        """全部已安装资产（键为 plugin_id）：构造期水合的唯一来源。"""
        ...

    def put(self, plugin_id: str, asset: InstallableAsset) -> None:
        """登记安装（`register` 后调用；同 id 覆盖）。"""
        ...

    def remove(self, plugin_id: str) -> bool:
        """清除安装记录（`uninstall` 时调用）；返回是否确有该条目。"""
        ...


class _HydratedPlugin:
    """水合用的最小插件载体（满足 ``Plugin`` 结构契约，load/unload/check 为 no-op）。

    ``plugin_registry`` 是 L0 基底、**不得** import ``core.tools.StubPlugin``（L1），故此处
    自带一份最小实现 —— 只为让 ``PluginRegistry.state/unload`` 认得**已落盘**的安装记录
    （否则跨进程 `plugin uninstall` 抛「插件未注册」）。

    manifest 来自**不可信的状态文件**，故三个字段按类型兜底：坏字段降级为默认值，
    **绝不**让一条坏账本记录阻断构造（规格「账本损坏或条目残缺降级」/「不阻断启动」）。
    """

    def __init__(self, plugin_id: str, manifest: dict[str, Any]) -> None:
        generation = manifest.get("generation", 1)
        schema = manifest.get("schema")
        coeffects = manifest.get("coeffects")
        self.plugin_id = plugin_id
        self.generation = generation if isinstance(generation, int) else 1
        self.schema: dict[str, Any] = (
            cast("dict[str, Any]", schema) if isinstance(schema, dict) else {"type": "object"}
        )
        self.coeffects: list[str] = (
            [item for item in cast("list[Any]", coeffects) if isinstance(item, str)]
            if isinstance(coeffects, list)
            else []
        )

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True


class PluginInstaller:
    """插件安装生命周期：
    discover → verify → install → register → activate → deactivate → uninstall。
    """

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        registry: PluginRegistry | None = None,
        *,
        source_resolver: SourceResolver | None = None,
        verifier: SignatureVerifier | None = None,
        installer: Installer | None = None,
        uninstaller: Uninstaller | None = None,
        store: InstallStore | None = None,
    ) -> None:
        self._registry = registry if registry is not None else PluginRegistry()
        self._source_resolver = source_resolver or _default_resolve
        self._verifier = verifier or _default_verify
        self._installer = installer or _default_install
        self._uninstaller = uninstaller or _default_uninstall
        self._store = store
        self._assets: dict[str, InstallableAsset] = {}
        if store is not None:
            self._hydrate(store.records())

    def _hydrate(self, records: dict[str, InstallableAsset]) -> None:
        """构造期水合：账本 → 进程内账本 + 注册表登记（跨进程 `list` / `uninstall` 的前提）。"""
        for plugin_id, asset in records.items():
            self._registry.register(_HydratedPlugin(plugin_id, asset.manifest))
            self._assets[plugin_id] = asset

    def discover(self, source: PluginSource, location: str, kind: PluginKind) -> InstallableAsset:
        try:
            manifest = self._source_resolver(source, location)
        except DomainError:
            raise
        except Exception as exc:  # noqa: BLE001 — 来源解析异常统一映射 SOURCE_NOT_FOUND
            raise DomainError(ErrorCode.SOURCE_NOT_FOUND, f"来源不可达: {exc}") from exc
        return InstallableAsset(kind=kind, source=source, manifest=manifest)

    def verify(self, asset: InstallableAsset, signature: str) -> None:
        if not self._verifier(asset, signature):
            raise DomainError(ErrorCode.SIGNATURE_INVALID, "签名校验失败或缺失")

    def install(self, asset: InstallableAsset) -> None:
        try:
            self._installer(asset)
        except DomainError:
            raise
        except Exception as exc:  # noqa: BLE001 — 安装异常统一映射 INSTALL_FAILED
            raise DomainError(ErrorCode.INSTALL_FAILED, f"安装失败: {exc}") from exc

    def register(self, asset: InstallableAsset, plugin: Plugin) -> None:
        self._registry.register(plugin)
        if self._store is not None:
            # 先落盘再入内存：落盘失败则整体失败、`_assets` 不被改动（不留半份登记）。
            self._store.put(plugin.plugin_id, asset)
        self._assets[plugin.plugin_id] = asset

    def activate(self, plugin_id: str) -> None:
        self._registry.load(plugin_id)
        self._registry.activate(plugin_id)

    def deactivate(self, plugin_id: str) -> None:
        self._registry.deactivate(plugin_id)

    def installed(self) -> list[dict[str, str]]:
        """返回已安装资产的清单（plugin_id/kind/source），供 list 命令与工具消费。"""
        return [
            {"plugin_id": pid, "kind": asset.kind.value, "source": asset.source.value}
            for pid, asset in sorted(self._assets.items())
        ]

    def uninstall(self, plugin_id: str) -> None:
        if plugin_id not in self._assets:
            raise DomainError(ErrorCode.UNINSTALL_NOT_FOUND, f"插件未安装: {plugin_id}")
        asset = self._assets[plugin_id]
        state = self._registry.state(plugin_id)
        if state is PluginState.ACTIVE:
            self._registry.deactivate(plugin_id)
        if state is not PluginState.UNLOADED:
            self._registry.unload(plugin_id)
        self._uninstaller(asset)  # 对称回退真实注册（skill 移除 / tool 卸载）
        if self._store is not None:
            self._store.remove(plugin_id)  # 物化回退成功才清账：失败则下次仍可重试
        self._assets.pop(plugin_id, None)
