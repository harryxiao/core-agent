"""MCP 消费侧安全接线测试（change 0054 / 账本 B1-M2）。

证明组合根真的把沙箱接进 MCP client，且 `InstallDispatcher` 消费同一实例
（否则 stdio 子进程不经沙箱、http 出站不经白名单）。
"""

from __future__ import annotations

import pytest

from core.configuration import ConfigManager
from core.runtime import build_runtime


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "  reasoning_effort: low\n",
        encoding="utf-8",
    )
    return str(cfg)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def test_build_runtime_assembles_mcp_client(runtime) -> None:
    """组合根产出非空 MCP client 且已注入沙箱。"""
    assert runtime.mcp_client is not None
    assert runtime.mcp_client._sandbox is not None  # noqa: SLF001 — 接线断言
    assert runtime.mcp_client._policy is not None  # noqa: SLF001 — 出站守卫接线


def test_install_dispatcher_shares_runtime_mcp_client(runtime) -> None:
    """插件安装分发器消费组合根同一 MCP client（唯一实例）。"""
    dispatcher = runtime.installer._installer.__self__  # noqa: SLF001 — 接线断言
    assert dispatcher._mcp is runtime.mcp_client  # noqa: SLF001 — 接线断言
