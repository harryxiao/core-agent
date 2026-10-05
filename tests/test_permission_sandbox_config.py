"""出站白名单可配（change 0071 / 账本 B5）。

规格「沙箱执行颗粒度」场景「网络出站白名单」要求出站目标**不在白名单即拦截**；而此前
白名单在生产**恒为空**（`runtime.py` 构造 `SandboxPolicy()` 不传参）—— 白名单不可配 ⇒
规格的「放行」半边在生产不可达（与 E15 同型缺陷）。本文件证明：

① `ConfigSpec` 单一真源三面（yaml / env / CLI）齐备且优先级链一致；
② yaml 子集解析器**不含列表**，故取值统一为**逗号分隔标量**，归一到裸主机名（去空白 / 去重）；
③ 非法条目（带 scheme / 端口 / 路径 / 内部空白）**校验期阻断**，不静默兜底成永不匹配；
④ 缺省空 = fail-closed 全拒（安全默认不变）；
⑤ 组合根**真的**把配置注入生产 `SandboxPolicy`，并端到端支配 http 出站守卫。
"""

from __future__ import annotations

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.mcp import MCPEndpoint, MCPError, MCPErrorCode
from core.permission import AccessControlError, SandboxManager
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)


def _write_config(tmp_path, permission: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + permission, encoding="utf-8")
    return str(cfg)


def _allowlist_yaml(raw: str) -> str:
    return f"permission:\n  sandbox:\n    host_allowlist: {raw}\n"


def _manager(
    tmp_path,
    permission: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
    load: bool = True,
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, permission),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    if load:
        manager.load()
    return manager


# ---- ConfigSpec 单一真源面 ----


def test_spec_declares_allowlist_key() -> None:
    """键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备（单一真源）。"""
    specs = {spec.key: spec for spec in config_specs()}
    spec = specs["permission.sandbox.host_allowlist"]
    assert spec.cli_flag == "--permission.sandbox.host-allowlist"
    assert spec.env_var == "CORE_SANDBOX_HOST_ALLOWLIST"
    assert spec.map_to == "permission.sandbox.host_allowlist"
    assert spec.default == ""  # 缺省空 = fail-closed 全拒


# ---- 缺省与三面覆盖 + 优先级链 ----


def test_default_is_empty_fail_closed(tmp_path) -> None:
    """未配置 permission 段 ⇒ 空白名单（全拒），与 change 0054 的行为逐位一致。"""
    assert _manager(tmp_path).sandbox_host_allowlist() == []


def test_yaml_csv_is_trimmed_and_deduped(tmp_path) -> None:
    """逗号分隔标量 → 裸主机名列表：去空白、去空项、保序去重。"""
    raw = " a.example.com , b.example.com ,, a.example.com "  # 含空白 / 空项 / 重复
    manager = _manager(tmp_path, _allowlist_yaml(f'"{raw}"'))
    assert manager.sandbox_host_allowlist() == ["a.example.com", "b.example.com"]


def test_fullwidth_comma_tolerated(tmp_path) -> None:
    """全角逗号同等对待（中文输入法下的常见误输，静默失配的代价是「配了却连不上」）。"""
    manager = _manager(tmp_path, _allowlist_yaml('"a.example.com，b.example.com"'))
    assert manager.sandbox_host_allowlist() == ["a.example.com", "b.example.com"]


def test_env_overrides_yaml(tmp_path) -> None:
    manager = _manager(
        tmp_path,
        _allowlist_yaml("yaml.example.com"),
        environ={"CORE_SANDBOX_HOST_ALLOWLIST": "env.example.com"},
    )
    assert manager.sandbox_host_allowlist() == ["env.example.com"]


def test_cli_overrides_env_and_yaml(tmp_path) -> None:
    """优先级链 CLI flag > env > config.yaml（配置能力的既有口径）。"""
    manager = _manager(
        tmp_path,
        _allowlist_yaml("yaml.example.com"),
        environ={"CORE_SANDBOX_HOST_ALLOWLIST": "env.example.com"},
        cli={"permission.sandbox.host_allowlist": "cli.example.com"},
    )
    assert manager.sandbox_host_allowlist() == ["cli.example.com"]


# ---- 非法取值校验期阻断（不静默兜底） ----


@pytest.mark.parametrize(
    "value",
    [
        "https://api.example.com",  # 带 scheme
        "api.example.com/v1",  # 带路径
        "api.example.com:443",  # 带端口
        "api example.com",  # 内部空白
    ],
)
def test_invalid_entries_block_startup(tmp_path, value: str) -> None:
    """`check_outbound` 的实参是 `urlparse(url).hostname`（不含 scheme/端口/路径）⇒
    这些条目**永不匹配**；静默接受的后果是「配了却连不上」，故校验期拒绝。"""
    with pytest.raises(ConfigurationError, match="非法出站白名单"):
        _manager(tmp_path, _allowlist_yaml(value))


def test_non_string_value_blocks_startup(tmp_path) -> None:
    """yaml 标量被解析成非字符串（如 `123`）→ 阻断，不退化成缺省。"""
    with pytest.raises(ConfigurationError, match="非法出站白名单取值"):
        _manager(tmp_path, _allowlist_yaml("123"))


def test_invalid_value_does_not_silently_fall_back(tmp_path) -> None:
    """非法取值**不得**退化成空白名单（否则配置错误被掩盖成「看起来正常」）。"""
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, _allowlist_yaml("api.example.com:443"))


# ---- 组合根注入 + 端到端 ----


@pytest.fixture
def state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _runtime_with_allowlist(tmp_path, raw: str):
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, _allowlist_yaml(raw))))


def _http_endpoint(host: str) -> MCPEndpoint:
    return MCPEndpoint(transport="http", url=f"https://{host}/mcp")


def test_build_runtime_injects_configured_allowlist(tmp_path, state_dir) -> None:
    """组合根按配置值构造策略，且客户端与沙箱管理器**共用同一实例**（单一真源）。"""
    runtime = _runtime_with_allowlist(tmp_path, '"mcp.example.com"')
    policy = runtime.mcp_client._policy  # noqa: SLF001 — 接线断言
    assert policy is runtime.mcp_client._sandbox._policy  # noqa: SLF001
    assert isinstance(runtime.mcp_client._sandbox, SandboxManager)  # noqa: SLF001
    policy.check_outbound("mcp.example.com")  # 白名单内放行
    with pytest.raises(AccessControlError, match="出站目标不在白名单"):
        policy.check_outbound("evil.example.com")


def test_configured_allowlist_governs_production_transport(tmp_path, state_dir) -> None:
    """端到端：配置真的支配生产 http 出站守卫（非纸面）。

    白名单内 → 越过守卫（止于 SDK 降级 / 会话待接入，码为 ``MCP_CONNECT_FAILED``）；
    白名单外 → ``PERMISSION_DENIED``（守卫先于一切网络动作）。
    """
    runtime = _runtime_with_allowlist(tmp_path, '"mcp.example.com"')
    with pytest.raises(MCPError) as allowed:
        runtime.mcp_client.connect(_http_endpoint("mcp.example.com"))
    assert allowed.value.code is MCPErrorCode.MCP_CONNECT_FAILED  # 守卫放行，止于后续
    with pytest.raises(MCPError) as denied:
        runtime.mcp_client.connect(_http_endpoint("evil.example.com"))
    assert denied.value.code is MCPErrorCode.PERMISSION_DENIED


def test_unconfigured_production_policy_denies_all_outbound(tmp_path, state_dir) -> None:
    """缺省（未配白名单）生产策略全拒 —— fail-closed 安全默认不得因本次变更松动。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    with pytest.raises(MCPError) as denied:
        runtime.mcp_client.connect(_http_endpoint("mcp.example.com"))
    assert denied.value.code is MCPErrorCode.PERMISSION_DENIED
