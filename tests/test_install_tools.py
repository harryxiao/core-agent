"""tool-use 插件安装工具单元测试（M3，契约 0028；组合根接线见 change 0108 / 账本 E33）。

覆盖：install 走 discover→verify→install→register→activate / uninstall 走
deactivate→卸载清理 / list 列出已装资产；外加组合根装配后三工具**生产可达**且与
`Runtime.installer` 同实例（含对称卸载）。
"""

from __future__ import annotations

import json

import pytest

from core.configuration import ConfigManager
from core.plugin_registry import PluginInstaller, PluginKind, PluginSource
from core.plugins import InstallRecord, PluginInstallRegistry, plugin_installs_path
from core.runtime import build_runtime
from core.tools import StubPlugin, install_tool, list_tool, uninstall_tool


def _installer() -> PluginInstaller:
    # 离线 resolver：不触真实网络/磁盘，manifest 由测试注入
    return PluginInstaller(source_resolver=lambda source, location: {})


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    return str(cfg)


def _runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def test_install_tool_registers_plugin() -> None:
    installer = _installer()
    tool = install_tool(installer)
    result = tool.handler(source="local-path", kind="skill", name="demo")
    assert result["installed"] == "installed.skill.demo"
    assert installer.installed() != []


def test_uninstall_tool_removes_plugin() -> None:
    installer = _installer()
    tool = install_tool(installer)
    tool.handler(source="local-path", kind="skill", name="demo")
    untool = uninstall_tool(installer)
    result = untool.handler("installed.skill.demo")
    assert result["uninstalled"] == "installed.skill.demo"
    assert installer.installed() == []


def test_list_tool_lists_installed() -> None:
    installer = _installer()
    tool = install_tool(installer)
    tool.handler(source="local-path", kind="skill", name="demo")
    ltool = list_tool(installer)
    result = ltool.handler()
    assert any(item["plugin_id"] == "installed.skill.demo" for item in result["installed"])


# ---- 组合根接线（change 0108 / 账本 E33）----


def test_install_tools_registered_in_runtime(monkeypatch, tmp_path) -> None:
    """三个插件安装工具须在**生产工具面**可达（规格「插件安装工具」），而非仅单测可调。"""
    runtime = _runtime(monkeypatch, tmp_path)
    ids = {t.tool_id for t in runtime.tools.active_tools()}
    assert {"tools.install", "tools.uninstall", "tools.list"} <= ids


def test_runtime_install_tool_uses_runtime_installer(monkeypatch, tmp_path) -> None:
    """注册进组合根的 install 工具与 `Runtime.installer` **同一实例**（否则装进一次性注册表）。"""
    runtime = _runtime(monkeypatch, tmp_path)
    install = runtime.tools._tools["tools.install"]  # noqa: SLF001 — 取 Tool（含 handler）验证同实例

    manifest = tmp_path / "skill.json"
    manifest.write_text(json.dumps({"skill_id": "skills.demo.hello"}), encoding="utf-8")
    result = install.handler(source="local-path", kind="skill", name=str(manifest))

    assert [item["plugin_id"] for item in runtime.installer.installed()] == [result["installed"]]


def test_runtime_installer_uninstalls_cli_tool(monkeypatch, tmp_path) -> None:
    """`Runtime.installer` 的卸载须走 dispatcher 对称回退（cli 工具真从工具面摘除）。"""
    runtime = _runtime(monkeypatch, tmp_path)
    manifest = tmp_path / "cli.json"
    manifest.write_text(json.dumps({"name": "echo", "command": "echo"}), encoding="utf-8")

    asset = runtime.installer.discover(PluginSource.LOCAL_PATH, str(manifest), PluginKind.CLI)
    runtime.installer.install(asset)
    runtime.installer.register(asset, StubPlugin("cli.echo", asset.manifest))
    assert "cli.echo" in {t.tool_id for t in runtime.tools.active_tools()}

    runtime.installer.uninstall("cli.echo")
    assert "cli.echo" not in {t.tool_id for t in runtime.tools.active_tools()}


# ---- 装配期重建（change 0109 / 账本 E36）----


def _seed_install(*manifests: dict[str, object]) -> None:
    """预置账本记录（等价「上一进程 `plugin install --kind cli` 装过」）。"""
    registry = PluginInstallRegistry(plugin_installs_path())
    for manifest in manifests:
        registry.put(
            InstallRecord(
                plugin_id=str(manifest.get("name")),
                kind=PluginKind.CLI,
                source=PluginSource.LOCAL_PATH,
                manifest=manifest,
            )
        )


def _seeded_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def test_runtime_rebuilds_cli_install_from_ledger(monkeypatch, tmp_path) -> None:
    """账本记录在装配期经**同一安装管线**重建 ⇒ 重启后 `cli.*` 仍在生产工具面。"""
    _seed_install({"name": "demo", "command": "echo"})
    runtime = _seeded_runtime(monkeypatch, tmp_path)
    assert "cli.demo" in {t.tool_id for t in runtime.tools.active_tools()}


def test_runtime_skips_unrebuildable_record(monkeypatch, tmp_path) -> None:
    """坏记录（cli 缺 command）只告警跳过：其余记录照常重建，装配不阻断。"""
    _seed_install({"name": "demo", "command": "echo"}, {"name": "broken"})
    with pytest.warns(UserWarning, match="插件安装记录"):
        runtime = _seeded_runtime(monkeypatch, tmp_path)
    assert "cli.demo" in {t.tool_id for t in runtime.tools.active_tools()}
