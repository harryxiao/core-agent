"""Phase 16 插件/工具链路缺口补齐测试（M9 修复补丁）。

覆盖三条链路的真实断言：③ coeffect 贯通（内置文件工具可执行 / 缺失拒绝）；
② 安装分发（按 PluginKind 命中 skill / mcp / cli 真实注册）；① CLI 执行
（subprocess 真进程 + 结构化结果 + 非零退出码承载）；外加门控回归与组合根接线。
"""

from __future__ import annotations

from core.configuration import ConfigManager
from core.mcp import FakeTransport, MCPClient
from core.plugin_registry import (
    CoeffectResolver,
    InstallableAsset,
    PluginInstaller,
    PluginKind,
    PluginSource,
)
from core.plugins import CLIAdapter, InstallDispatcher
from core.runtime import build_runtime
from core.skills import SkillLibrary
from core.tools import (
    GateDecision,
    SafetyGate,
    StubPlugin,
    ToolErrorCode,
    ToolProvider,
    file_patch,
    file_read,
    file_write,
)


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


# ---- ③ coeffect 贯通 ----


def test_coeffect_resolver_enables_builtin_file_tools(tmp_path) -> None:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    for tool in (file_read(), file_write(), file_patch()):
        provider.register(tool)

    target = tmp_path / "a.txt"
    target.write_text("hello\nworld\n", encoding="utf-8")
    result = provider.invoke("tools.file_read", {"path": str(target)}, trace_id="t1")

    assert result.ok
    assert result.data["content"] == "hello\nworld"


def test_unregistered_coeffect_returns_missing(tmp_path) -> None:
    provider = ToolProvider()  # 空 resolver：未注册任何 coeffect 来源
    provider.register(file_read())
    result = provider.invoke("tools.file_read", {"path": str(tmp_path / "x")}, trace_id="t1")

    assert not result.ok
    assert result.error is not None
    assert result.error.code == ToolErrorCode.COEFFECT_MISSING


# ---- ② 安装分发 ----


def test_install_dispatch_by_kind() -> None:
    skill_library = SkillLibrary()
    provider = ToolProvider()
    transport = FakeTransport()
    transport.add_tool("search", "d")
    mcp_client = MCPClient(transport_factory=lambda ep: transport)
    dispatcher = InstallDispatcher(skill_library, provider, mcp_client=mcp_client)

    manifests = {
        "skill-loc": {"skill_id": "skills.data.sum", "description": "d", "param_schema": {}},
        "mcp-loc": {"url": "https://example.com/mcp", "name": "files"},
        "cli-loc": {"name": "echo", "command": "echo", "args": ["hi"]},
    }

    def fake_resolve(_source, location):
        return manifests[location]

    installer = PluginInstaller(source_resolver=fake_resolve, installer=dispatcher.install)

    skill_asset = installer.discover(PluginSource.LOCAL_PATH, "skill-loc", PluginKind.SKILL)
    installer.install(skill_asset)
    assert skill_library.lookup("skills.data.sum").skill_id == "skills.data.sum"

    mcp_asset = installer.discover(PluginSource.LOCAL_PATH, "mcp-loc", PluginKind.MCP)
    installer.install(mcp_asset)
    ids = {t.tool_id for t in provider.active_tools()}
    assert any(i.startswith("mcp.") and i.endswith(".search") for i in ids)

    cli_asset = installer.discover(PluginSource.LOCAL_PATH, "cli-loc", PluginKind.CLI)
    installer.install(cli_asset)
    assert "cli.echo" in {t.tool_id for t in provider.active_tools()}


def test_uninstall_reverses_dispatch_by_kind() -> None:
    """uninstall 对称回退 install 的真实注册：skill 移除 / mcp+cli 工具卸载。"""
    skill_library = SkillLibrary()
    provider = ToolProvider()
    transport = FakeTransport()
    transport.add_tool("search", "d")
    mcp_client = MCPClient(transport_factory=lambda ep: transport)
    dispatcher = InstallDispatcher(skill_library, provider, mcp_client=mcp_client)

    manifests = {
        "skill-loc": {"skill_id": "skills.data.sum", "description": "d", "param_schema": {}},
        "mcp-loc": {"url": "https://example.com/mcp", "name": "files"},
        "cli-loc": {"name": "echo", "command": "echo", "args": ["hi"]},
    }

    def fake_resolve(_source, location):
        return manifests[location]

    installer = PluginInstaller(
        source_resolver=fake_resolve,
        installer=dispatcher.install,
        uninstaller=dispatcher.uninstall,
    )

    for key, kind, plugin_id in (
        ("skill-loc", PluginKind.SKILL, "skills.data.sum"),
        ("mcp-loc", PluginKind.MCP, "mcp.files"),
        ("cli-loc", PluginKind.CLI, "cli.echo"),
    ):
        asset = installer.discover(PluginSource.LOCAL_PATH, key, kind)
        installer.install(asset)
        installer.register(asset, StubPlugin(plugin_id, asset.manifest))

    assert skill_library.lookup("skills.data.sum").skill_id == "skills.data.sum"
    ids = {t.tool_id for t in provider.active_tools()}
    assert any(i.startswith("mcp.") and i.endswith(".search") for i in ids)
    assert "cli.echo" in ids

    for plugin_id in ("skills.data.sum", "mcp.files", "cli.echo"):
        installer.uninstall(plugin_id)

    assert skill_library.all_skills() == []
    assert provider.active_tools() == []
    assert installer.installed() == []


# ---- ① CLI 执行 ----


def test_cli_adapter_executes_command() -> None:
    adapter = CLIAdapter()
    asset = InstallableAsset(
        kind=PluginKind.CLI,
        source=PluginSource.LOCAL_PATH,
        manifest={"name": "echo", "command": "echo", "args": ["hello"]},
    )
    provider = ToolProvider()
    provider.register(adapter.adapt(asset))

    result = provider.invoke("cli.echo", {}, trace_id="t1")

    assert result.ok
    assert result.data["returncode"] == 0
    assert result.data["stdout"].strip() == "hello"


def test_cli_adapter_nonzero_exit_carries_code() -> None:
    adapter = CLIAdapter()
    asset = InstallableAsset(
        kind=PluginKind.CLI,
        source=PluginSource.LOCAL_PATH,
        manifest={"name": "fail", "command": "false"},
    )
    provider = ToolProvider()
    provider.register(adapter.adapt(asset))

    result = provider.invoke("cli.fail", {}, trace_id="t1")

    assert result.ok  # subprocess 已运行；退出码与错误码在 data 中结构化承载
    assert result.data["returncode"] != 0
    assert result.data["code"] == "CLI_NONZERO_EXIT"


# ---- 门控回归 ----


def test_gate_deny_precedes_cli_execution() -> None:
    adapter = CLIAdapter()
    asset = InstallableAsset(
        kind=PluginKind.CLI,
        source=PluginSource.LOCAL_PATH,
        manifest={"name": "echo", "command": "echo", "args": ["hi"]},
    )

    class _DenyGate(SafetyGate):
        def confirm(self, tool_id, args, coeffects, reversible):
            return GateDecision("deny", "blocked")

    provider = ToolProvider(gate=_DenyGate())
    provider.register(adapter.adapt(asset))

    result = provider.invoke("cli.echo", {}, trace_id="t1")

    assert not result.ok
    assert result.error is not None
    assert result.error.code == ToolErrorCode.GATE_DENIED


# ---- 组合根接线 ----


def test_build_runtime_wires_installer_and_coeffects(monkeypatch, tmp_path) -> None:
    """走真装配路径（非手建 resolver）：build_runtime 注入的 resolver 必须让
    filesystem:read / filesystem:write 两个 coeffect 都 resolve 通过并执行。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    target = tmp_path / "a.txt"
    target.write_text("hello\n", encoding="utf-8")
    read = runtime.tools.invoke("tools.file_read", {"path": str(target)}, trace_id="t1")
    assert read.ok
    assert read.data["content"] == "hello"

    out = tmp_path / "b.txt"
    write = runtime.tools.invoke(
        "tools.file_write", {"path": str(out), "content": "written"}, trace_id="t2"
    )
    assert write.ok
    assert out.read_text(encoding="utf-8") == "written"

    assert runtime.installer is not None
