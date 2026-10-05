"""插件安装账本与按 kind 路由的单一视图（change 0109 / 账本 E36）。

规格「插件安装持久化」要求「已安装」**跨进程可证**：安装账本原先是
``PluginInstaller._assets`` 这个**进程内字典** ⇒ `plugin list` 恒空、`plugin uninstall`
恒 `UNINSTALL_NOT_FOUND`，对**所有** kind 都跨进程失效（skill 只是「物化」侥幸落进
``skills.json``，账本仍空）。

本文件证明：账本落盘/读回/覆盖且**原子写**、损坏与残缺条目**降级告警**；
``PluginInstallStore`` 按 kind **路由**（mcp → ``mcp-endpoints.json``，**不**二次记账）
且 ``records()`` 给出**合并视图**；``PluginInstaller`` 注入 store 后 ``register`` 落盘、
``uninstall`` 清条目、**构造期水合**（新实例即见既有记录且可卸载）；卸载幂等
（账本条目陈旧、物化已不在时不抛裸 ``KeyError``）。
"""

from __future__ import annotations

import json
import os
import pathlib
import warnings

import pytest

from core.mcp.endpoints import MCPEndpointRegistry
from core.plugin_registry import (
    DomainError,
    ErrorCode,
    InstallableAsset,
    PluginInstaller,
    PluginKind,
    PluginSource,
)
from core.plugins import (
    InstallDispatcher,
    InstallRecord,
    PluginInstallRegistry,
    PluginInstallStore,
    plugin_installs_path,
)
from core.skills import SkillLibrary
from core.tools import StubPlugin, ToolProvider

_LEDGER = "plugin-installs.json"
_ENDPOINTS = "mcp-endpoints.json"


def _asset(kind: PluginKind, **manifest: object) -> InstallableAsset:
    """测试资产：来源固定 local-path，manifest 即入参（skill/cli/mcp 三种口径各取所需）。"""
    return InstallableAsset(kind=kind, source=PluginSource.LOCAL_PATH, manifest=dict(manifest))


def _record(asset: InstallableAsset, plugin_id: str = "installed.cli.demo") -> InstallRecord:
    """测试构造：资产 → 账本记录（plugin_id 缺省取 `installed.cli.<name>` 口径）。"""
    return InstallRecord(
        plugin_id=plugin_id, kind=asset.kind, source=asset.source, manifest=dict(asset.manifest)
    )


def _registry(root: pathlib.Path) -> PluginInstallRegistry:
    return PluginInstallRegistry(root / _LEDGER)


def _store(root: pathlib.Path) -> PluginInstallStore:
    return PluginInstallStore(
        PluginInstallRegistry(root / _LEDGER), MCPEndpointRegistry(root / _ENDPOINTS)
    )


def _dispatcher(root: pathlib.Path) -> InstallDispatcher:
    return InstallDispatcher(
        skill_library=SkillLibrary(path=root / "skills.json"), tool_provider=ToolProvider()
    )


def _cli_asset(name: str = "demo", command: str = "echo") -> InstallableAsset:
    return _asset(PluginKind.CLI, name=name, command=command, args=["hi"])


# ---- ① 账本：往返 / 覆盖 / 原子写 / 降级 ----


def test_path_uses_state_dir(monkeypatch, tmp_path) -> None:
    """账本落 ``$CORE_STATE_DIR``（与 skills.json / mcp-endpoints.json 同状态目录约定）。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    assert plugin_installs_path() == tmp_path / "state" / _LEDGER


def test_put_persists_across_instances(tmp_path) -> None:
    """`plugin install` 的成果必须活过**一次性进程** —— 新实例（新进程）读得到。"""
    _registry(tmp_path).put(_record(_cli_asset()))
    assert [r.plugin_id for r in _registry(tmp_path).list()] == ["installed.cli.demo"]


def test_file_is_json_object_with_version(tmp_path) -> None:
    """落盘是带版本的单文件 JSON（对齐 mcp-endpoints.json 的状态文件约定）。"""
    _registry(tmp_path).put(_record(_cli_asset()))
    raw = json.loads((tmp_path / _LEDGER).read_text(encoding="utf-8"))
    assert raw["installs"]["installed.cli.demo"]["kind"] == "cli"


def test_put_overwrites_same_plugin_id(tmp_path) -> None:
    """重装同一 plugin_id **覆盖**（重装即升级），不因重名拒绝。"""
    registry = _registry(tmp_path)
    registry.put(_record(_cli_asset()))
    registry.put(_record(_cli_asset(command="echo2")))
    records = registry.list()
    assert [r.plugin_id for r in records] == ["installed.cli.demo"]
    assert records[0].asset().manifest["command"] == "echo2"


def test_remove_persists_and_reports_missing(tmp_path) -> None:
    _registry(tmp_path).put(_record(_cli_asset()))
    assert _registry(tmp_path).remove("installed.cli.demo") is True
    assert _registry(tmp_path).list() == []
    assert _registry(tmp_path).remove("installed.cli.demo") is False  # 二次移除：未安装


def test_missing_file_is_empty_and_silent(tmp_path) -> None:
    """无账本（从未装过）是**正常态**：空列表且不告警。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _registry(tmp_path).list() == []


def test_interrupted_write_keeps_previous_file(tmp_path, monkeypatch) -> None:
    """原子写（tmp + os.replace）：写入中途失败**不损坏**既有账本。"""
    registry = _registry(tmp_path)
    registry.put(_record(_cli_asset()))

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("进程在写入中途被终止")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        registry.put(_record(_cli_asset(), plugin_id="second"))

    assert [r.plugin_id for r in _registry(tmp_path).list()] == ["installed.cli.demo"]


def test_corrupt_file_warns_and_degrades(tmp_path) -> None:
    """文件损坏 → 告警 + 视为空（不静默丢弃、不阻断启动）。"""
    (tmp_path / _LEDGER).write_text("{ 这不是 JSON", encoding="utf-8")
    with pytest.warns(UserWarning, match="账本"):
        assert _registry(tmp_path).list() == []


def test_malformed_entry_skipped_others_kept(tmp_path) -> None:
    """残缺条目（缺 plugin_id / kind）只跳过该条，其余照常生效。"""
    (tmp_path / _LEDGER).write_text(
        json.dumps(
            {
                "version": 1,
                "installs": {
                    "ok": {
                        "plugin_id": "ok",
                        "kind": "cli",
                        "source": "local-path",
                        "manifest": {},
                    },
                    "broken": {"plugin_id": "broken", "source": "local-path"},
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.warns(UserWarning, match="broken"):
        records = _registry(tmp_path).list()
    assert [r.plugin_id for r in records] == ["ok"]


# ---- ② store：按 kind 路由 + 合并视图 ----


def test_store_routes_cli_to_ledger(tmp_path) -> None:
    _store(tmp_path).put("installed.cli.demo", _cli_asset())
    assert [r.plugin_id for r in _registry(tmp_path).list()] == ["installed.cli.demo"]


def test_store_routes_mcp_to_endpoint_registry(tmp_path) -> None:
    """mcp 类持久化真源是端点注册表（与 `mcp add` 同一处），**不**在本账本二次记账。"""
    _store(tmp_path).put(
        "files", _asset(PluginKind.MCP, name="files", url="npx -y srv", transport="stdio")
    )
    endpoints = MCPEndpointRegistry(tmp_path / _ENDPOINTS).list()
    assert [(r.name, r.source, r.transport) for r in endpoints] == [
        ("files", "npx -y srv", "stdio")
    ]
    assert not (tmp_path / _LEDGER).exists()


def test_store_records_merges_both_views(tmp_path) -> None:
    """`records()` = 账本 + 端点注册表的合并视图（`list` / `uninstall` 的单一真源）。"""
    store = _store(tmp_path)
    store.put("installed.cli.demo", _cli_asset())
    store.put("files", _asset(PluginKind.MCP, name="files", url="npx -y srv"))
    merged = store.records()
    assert sorted(merged) == ["files", "installed.cli.demo"]
    assert merged["files"].kind is PluginKind.MCP
    assert merged["installed.cli.demo"].kind is PluginKind.CLI


def test_store_remove_covers_both_views(tmp_path) -> None:
    store = _store(tmp_path)
    store.put("installed.cli.demo", _cli_asset())
    store.put("files", _asset(PluginKind.MCP, name="files", url="npx -y srv"))
    assert store.remove("installed.cli.demo") is True
    assert store.remove("files") is True
    assert store.records() == {}
    assert store.remove("files") is False  # 已移除：未安装


# ---- ③ PluginInstaller：落盘 / 水合 / 清账 ----


def test_installer_register_persists(tmp_path) -> None:
    installer = PluginInstaller(store=_store(tmp_path))
    asset = _cli_asset()
    installer.register(asset, StubPlugin("installed.cli.demo", dict(asset.manifest)))
    assert [r.plugin_id for r in _registry(tmp_path).list()] == ["installed.cli.demo"]


def test_installer_hydrates_from_store(tmp_path) -> None:
    """构造期水合：新实例（等价新进程）`installed()` 即见既有记录，且**可卸载**。"""
    first = PluginInstaller(store=_store(tmp_path))
    asset = _cli_asset()
    first.register(asset, StubPlugin("installed.cli.demo", dict(asset.manifest)))

    second = PluginInstaller(store=_store(tmp_path))  # 新进程
    assert second.installed() == [
        {"plugin_id": "installed.cli.demo", "kind": "cli", "source": "local-path"}
    ]
    second.uninstall("installed.cli.demo")  # 水合已登记插件 ⇒ 不抛「插件未注册」
    assert second.installed() == []


def test_installer_uninstall_clears_ledger(tmp_path) -> None:
    """卸载须**对称回退**物化并清除账本条目（否则新进程仍显示已安装）。"""
    skills = SkillLibrary(path=tmp_path / "skills.json")
    dispatcher = _dispatcher(tmp_path)
    installer = PluginInstaller(
        store=_store(tmp_path), installer=dispatcher.install, uninstaller=dispatcher.uninstall
    )
    asset = _asset(PluginKind.SKILL, skill_id="demo.skill", description="d")
    installer.install(asset)
    installer.register(asset, StubPlugin("demo.skill", dict(asset.manifest)))

    installer.uninstall("demo.skill")
    assert _registry(tmp_path).list() == []
    with pytest.raises(KeyError):
        skills.lookup("demo.skill")


def test_installer_without_store_keeps_in_memory_behaviour(tmp_path) -> None:
    """不注入 store ⇒ 行为与既有进程内账本一致（向后兼容，不落盘）。"""
    installer = PluginInstaller()
    asset = _cli_asset()
    installer.register(asset, StubPlugin("installed.cli.demo", dict(asset.manifest)))
    assert installer.installed()[0]["plugin_id"] == "installed.cli.demo"
    assert _registry(tmp_path).list() == []


def test_uninstall_missing_still_reports_not_found(tmp_path) -> None:
    """键不在账本与端点注册表中 ⇒ `UNINSTALL_NOT_FOUND`（现状语义不变）。"""
    installer = PluginInstaller(store=_store(tmp_path))
    with pytest.raises(DomainError) as exc:
        installer.uninstall("ghost")
    assert exc.value.code is ErrorCode.UNINSTALL_NOT_FOUND


# ---- ④ 卸载幂等：账本条目陈旧（物化已被外部移除） ----


def test_uninstall_skill_is_idempotent_when_absent(tmp_path) -> None:
    """账本条目可能陈旧（技能已在别处移除）⇒ 卸载须幂等，不抛裸 ``KeyError``。"""
    dispatcher = _dispatcher(tmp_path)
    asset = _asset(PluginKind.SKILL, skill_id="ghost.skill")
    dispatcher.uninstall(asset)  # 技能本就不在
    dispatcher.uninstall(asset)


def test_uninstall_cli_tool_is_idempotent(tmp_path) -> None:
    dispatcher = _dispatcher(tmp_path)
    dispatcher.uninstall(_cli_asset())  # 工具未注册：unregister 静默忽略
