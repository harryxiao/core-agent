"""MCP 端点注册表与 CLI 接线（change 0074 / 账本 B4）。

规格「MCP Server 安装与移除」以 **CLI 面**写场景（「WHEN 执行 mcp add / mcp remove」），
而 `entry._mcp` 对非 `serve` 子命令落兜底「已识别，尚未接线」⇒ 场景在生产不可达。
安装管线本身齐备（change `0054`），缺三件：**CLI 接线**、**端点跨进程持久化**
（CLI 是一次性进程，不落盘则 add 连上即丢）、**稳定工具命名**
（`connect` 原用 `uuid4()` 作 handle_id ⇒ `mcp.<uuid>.<工具>` 每次都变）。

本文件证明：注册表落盘/读回/删除且**原子写**、损坏与残缺条目**降级告警**、
命名安装的工具名**跨进程稳定** `mcp.<端点名>.<工具>`、装配期注册远端工具、
**不可达端点只告警不阻断装配**，以及 `mcp add/list/remove` 的 CLI 端到端（真实子进程）。
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import warnings

import pytest

from core.configuration import ConfigManager
from core.mcp import MCPClient, MCPError, MCPErrorCode, MCPToolAdapter
from core.mcp.endpoints import (
    EndpointRecord,
    MCPEndpointRegistry,
    default_endpoint_name,
    mcp_endpoints_path,
)
from core.runtime import build_runtime

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

# 最小 stdlib MCP 服务端（与 tests/test_mcp_stdio.py 同形）：initialize / tools/list / tools/call。
_ECHO_SERVER = """
import json, sys
def send(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    rid = msg.get("id")
    if rid is None:
        continue
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05"}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": [
            {"name": "echo", "description": "d", "inputSchema": {"type": "object"}}]})
    elif method == "tools/call":
        send({"jsonrpc": "2.0", "id": rid,
              "result": {"result": "ok", "args": msg["params"]["arguments"]}})
    else:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": method}})
"""

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)

_ECHO_TOOL_ID = "mcp.files.echo"


@pytest.fixture
def state_dir(monkeypatch, tmp_path):
    """隔离状态目录：注册表落 $CORE_STATE_DIR，装配期从这里读。"""
    state = tmp_path / "state"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(state))
    return state


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    return str(cfg)


def _server_source(tmp_path) -> str:
    """echo server 落文件 → 命令行来源字符串（`shlex.split` 友好，含空白/引号不炸）。"""
    script = tmp_path / "echo_server.py"
    script.write_text(_ECHO_SERVER, encoding="utf-8")
    return f"{sys.executable} {script}"


def _registry(path: pathlib.Path | None = None) -> MCPEndpointRegistry:
    return MCPEndpointRegistry(path if path is not None else mcp_endpoints_path())


# ---- ① 注册表：落盘 / 读回 / 删除 ----


def test_add_persists_across_instances(tmp_path) -> None:
    """`mcp add` 的成果必须活过一次性进程 —— 新实例（新进程）读得到。"""
    path = tmp_path / "mcp-endpoints.json"
    record = EndpointRecord(name="files", source="npx -y srv /tmp")
    _registry(path).add(record)
    assert _registry(path).list() == [record]


def test_file_is_json_object_with_version(tmp_path) -> None:
    """落盘是带版本的单文件 JSON（对齐 pets.json / evolution-pending.json 的状态文件约定）。"""
    path = tmp_path / "mcp-endpoints.json"
    _registry(path).add(EndpointRecord(name="files", source="srv"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["endpoints"]["files"]["source"] == "srv"


def test_remove_persists_and_reports_missing(tmp_path) -> None:
    path = tmp_path / "mcp-endpoints.json"
    _registry(path).add(EndpointRecord(name="files", source="srv"))
    assert _registry(path).remove("files") is True
    assert _registry(path).list() == []
    assert _registry(path).remove("files") is False  # 二次移除：未安装


def test_missing_file_is_empty_and_silent(tmp_path) -> None:
    """无注册表（从未 add 过）是**正常态**：空列表且不告警（多数用户没有 MCP 端点）。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _registry(tmp_path / "absent.json").list() == []


def test_duplicate_name_rejected(tmp_path) -> None:
    """重名拒绝（不静默覆盖）：派生名可能撞车（两条 `npx …` 都派生 `npx`）。"""
    path = tmp_path / "mcp-endpoints.json"
    _registry(path).add(EndpointRecord(name="files", source="srv-a"))
    with pytest.raises(MCPError) as exc:
        _registry(path).add(EndpointRecord(name="files", source="srv-b"))
    assert exc.value.code is MCPErrorCode.ENDPOINT_NAME_CONFLICT
    assert _registry(path).list()[0].source == "srv-a"  # 既有配置未被覆盖


def test_interrupted_write_keeps_previous_file(tmp_path, monkeypatch) -> None:
    """原子写（tmp + os.replace）：写入中途失败**不损坏**既有注册表（同 change 0062 口径）。"""
    path = tmp_path / "mcp-endpoints.json"
    first = EndpointRecord(name="files", source="srv-a")
    _registry(path).add(first)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("进程在写入中途被终止")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        _registry(path).add(EndpointRecord(name="other", source="srv-b"))

    assert _registry(path).list() == [first]  # 旧内容完好（非半写、非空）


def test_corrupt_file_warns_and_degrades(tmp_path) -> None:
    """文件损坏 → 告警 + 视为空（不静默丢弃、不阻断启动）。"""
    path = tmp_path / "mcp-endpoints.json"
    path.write_text("{ 这不是 JSON", encoding="utf-8")
    with pytest.warns(UserWarning, match="注册表"):
        assert _registry(path).list() == []


def test_malformed_entry_skipped_others_kept(tmp_path) -> None:
    """残缺条目（缺 name / source）只跳过该条，其余照常生效。"""
    path = tmp_path / "mcp-endpoints.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "endpoints": {
                    "files": {"name": "files", "source": "srv-a"},
                    "broken": {"name": "broken"},
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.warns(UserWarning, match="broken"):
        records = _registry(path).list()
    assert [r.name for r in records] == ["files"]


# ---- ② 名称派生 + manifest 形状 ----


def test_default_name_from_url_uses_host() -> None:
    assert default_endpoint_name("https://api.example.com/mcp") == "api.example.com"


def test_default_name_from_command_uses_basename() -> None:
    assert default_endpoint_name("/usr/local/bin/mcp-server --port 9") == "mcp-server"


def test_manifest_matches_install_pipeline() -> None:
    """记录 → manifest 的形状与 `InstallDispatcher._install_mcp` 的消费口径一致（单一解析点）。"""
    record = EndpointRecord(name="files", source="npx -y srv", transport="stdio", args=["a"])
    manifest = record.manifest()
    assert manifest["name"] == "files"
    assert manifest["endpoint"] == "npx -y srv"
    assert manifest["transport"] == "stdio"
    assert manifest["args"] == ["a"]


# ---- ③ 稳定命名（持久化的前提） ----


def test_named_install_tool_id_is_stable_across_clients(tmp_path) -> None:
    """同一安装名 → 同一工具名 `mcp.<端点名>.<工具>`（跨进程/跨连接逐字相同）。

    改前 `handle_id` 是 `uuid4()` ⇒ 每次连接工具名都变，按名授权 / 白名单 / 记忆引用无从谈起。
    """
    source = _server_source(tmp_path)
    seen: list[str] = []
    for _ in range(2):
        client = MCPClient()
        handle = client.add(source, "files")
        remote = client.list_tools(handle)[0]
        seen.append(MCPToolAdapter().adapt(remote, handle).tool_id)
        client.unload()
    assert seen == [_ECHO_TOOL_ID, _ECHO_TOOL_ID]


def test_reinstall_same_name_releases_previous_connection(tmp_path) -> None:
    """同名重装先释放旧连接（不留半开的子进程 / socket）。"""
    source = _server_source(tmp_path)
    client = MCPClient()
    client.add(source, "files")
    client.add(source, "files")
    assert len(client._transports) == 1  # noqa: SLF001 — 接线断言
    client.unload()


# ---- ④ 装配期：注册远端工具 + 不可达降级 ----


def _seed_endpoints(*records: EndpointRecord) -> None:
    registry = _registry()
    for record in records:
        registry.add(record)


def _tool_ids(runtime) -> list[str]:
    return [tool.tool_id for tool in runtime.tools.active_tools()]


def test_assembly_registers_remote_tools(tmp_path, state_dir) -> None:
    """装配期读注册表 → 连接 → 远端工具进本地工具集（规格「其工具可被动态发现」）。"""
    _seed_endpoints(EndpointRecord(name="files", source=_server_source(tmp_path)))
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    try:
        assert _ECHO_TOOL_ID in _tool_ids(runtime)
    finally:
        runtime.mcp_client.unload()  # 关掉 echo server 子进程（否则测试进程退出前泄漏）


def test_unreachable_endpoint_degrades_without_blocking(tmp_path, state_dir) -> None:
    """坏端点（命令不存在）只告警：装配照常完成，可达端点的工具仍注册。"""
    _seed_endpoints(
        EndpointRecord(name="files", source=_server_source(tmp_path)),
        EndpointRecord(name="dead", source="/nonexistent/mcp-server-xyz"),
    )
    with pytest.warns(UserWarning, match="dead"):
        runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    try:
        assert _ECHO_TOOL_ID in _tool_ids(runtime)
    finally:
        runtime.mcp_client.unload()


def test_empty_registry_does_not_change_assembly(tmp_path, state_dir) -> None:
    """未装端点（无注册表）⇒ 装配行为与本次变更前逐位一致（无连接、无告警）。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    assert not [tid for tid in _tool_ids(runtime) if tid.startswith("mcp.")]


# ---- ⑤ CLI 端到端（真实子进程） ----

_BOOTSTRAP = "from core.entry import main\nraise SystemExit(main({argv!r}))\n"


def _cli(*argv: str, state: pathlib.Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(_SRC),
        "CORE_STATE_DIR": str(state),
        "OPENAI_API_KEY": "sk-test",
    }
    env.pop("CORE_SANDBOX_HOST_ALLOWLIST", None)
    return subprocess.run(
        [sys.executable, "-c", _BOOTSTRAP.format(argv=list(argv))],
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_add_list_remove_roundtrip(tmp_path, state_dir) -> None:
    """`mcp add` → `mcp list` → `mcp remove`：安装成果跨**进程**可见（落盘的非纸面证据）。"""
    config = _write_config(tmp_path)
    added = _cli(
        "--config",
        config,
        "mcp",
        "add",
        _server_source(tmp_path),
        "--name",
        "files",
        state=state_dir,
    )
    assert added.returncode == 0, added.stderr
    assert _ECHO_TOOL_ID in added.stdout  # 发现的工具（含稳定命名）

    listed = _cli("mcp", "list", state=state_dir)
    assert listed.returncode == 0, listed.stderr
    assert "files" in listed.stdout

    removed = _cli("mcp", "remove", "files", state=state_dir)
    assert removed.returncode == 0, removed.stderr
    assert "files" not in _cli("mcp", "list", state=state_dir).stdout


def test_cli_add_unreachable_does_not_persist(tmp_path, state_dir) -> None:
    """连不上**不落盘** —— 不把打不通的端点持久化（此后每次装配徒劳重试）。"""
    result = _cli(
        "--config",
        _write_config(tmp_path),
        "mcp",
        "add",
        "/nonexistent/mcp-server-xyz",
        "--name",
        "dead",
        state=state_dir,
    )
    assert result.returncode != 0
    assert not mcp_endpoints_path().exists() or "dead" not in mcp_endpoints_path().read_text(
        encoding="utf-8"
    )


def test_cli_add_duplicate_name_rejected(tmp_path, state_dir) -> None:
    source = _server_source(tmp_path)
    config = _write_config(tmp_path)
    first = _cli("--config", config, "mcp", "add", source, "--name", "files", state=state_dir)
    assert first.returncode == 0, first.stderr
    again = _cli("--config", config, "mcp", "add", source, "--name", "files", state=state_dir)
    assert again.returncode != 0
    assert "已存在" in again.stderr


def test_cli_remove_unknown_name_fails(state_dir) -> None:
    result = _cli("mcp", "remove", "nope", state=state_dir)
    assert result.returncode != 0
    assert "未安装" in result.stderr


def test_cli_list_empty_when_nothing_installed(state_dir) -> None:
    result = _cli("mcp", "list", state=state_dir)
    assert result.returncode == 0, result.stderr
    assert "已安装 MCP 端点" in result.stdout  # 表头恒在，无端点时为空表
