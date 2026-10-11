"""容错件接线（change 0209 / ADR-0199 / 台账 E146）单元 + 配置 + 接线测试。

覆盖：Retry 进生产 —— 可逆工具执行类失败（超时 / 执行异常）后按退避重试、成功即止且**只记一次**
效应；不可逆工具不重试；策略拒绝不重试；耗尽**原样返回**最后失败结果（不降级）；`retry_attempts`
缺省 `0` ⇒ 组合根不包裹执行接缝（既有路径逐字不变）；配置三面（spec 声明 + yaml + env）＋ 非法值
阻断启动。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.constraints import RetryPolicy
from core.loop import Action, ActionResult, DefaultLoop
from core.loop.fault_adapter import FaultChain
from core.plugin_registry import EffectTracker
from core.runtime import build_runtime
from core.tools import Tool, ToolDef, ToolProvider

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


async def _no_sleep(_seconds: float) -> None:
    return None


def _tool(
    *,
    tool_id: str = "tools.flaky",
    handler: Any,
    reversible: bool,
    undo: Any = None,
) -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id=tool_id,
            description="",
            schema={"type": "object"},
            coeffects=[],
            reversible=reversible,
        ),
        handler=handler,
        undo=undo,
    )


def _plan(action: Action) -> Any:
    """planner：第 1 步给工具动作，之后给终止动作（本轮结束）。"""

    def plan(ctx: Any) -> Action:
        if ctx.rounds == 0:
            return action
        return Action(args={"reply": "done"})

    return plan


def _loop(provider: ToolProvider, chain: FaultChain | None) -> DefaultLoop:
    return DefaultLoop(
        planner=_plan(Action(tool_id="tools.flaky", args={})),
        tools=provider,
        act_wrapper=chain.wrap if chain is not None else None,
        max_rounds=5,
    )


def _chain(provider: ToolProvider, *, max_attempts: int = 3) -> FaultChain:
    return FaultChain(
        provider,
        RetryPolicy(max_attempts=max_attempts, base_delay=0.0, jitter=0.0),
        sleep=_no_sleep,
    )


def _act(loop: DefaultLoop, tool_id: str) -> ActionResult:
    """直调执行接缝（绕开 planner），拿到结构化结果做精确断言。"""
    return asyncio.run(loop._act(Action(tool_id=tool_id, args={}), "t"))  # noqa: SLF001


# ---- 重试（进生产）----


def test_reversible_flaky_retries_then_succeeds() -> None:
    """可逆工具首次超时、重试成功 ⇒ 返回成功，且只记一次可逆效应（不双记账）。"""
    calls: list[int] = []
    undone: list[int] = []

    def handler(**_kw: Any) -> str:
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("slow")  # → ToolErrorCode.TIMEOUT
        return "ok"

    provider = ToolProvider(effect_tracker=EffectTracker())
    provider.register(
        _tool(handler=handler, reversible=True, undo=lambda: lambda: undone.append(1))
    )
    loop = _loop(provider, _chain(provider))
    result = _act(loop, "tools.flaky")

    assert len(calls) == 2  # noqa: PLR2004 — 首次超时 + 一次重试成功
    assert result.failed is False
    report = provider.rollback()
    assert len(report.reverted) == 1  # 只记一次效应：重试不双记账
    assert undone == [1]


def test_reversible_flaky_e2e_through_loop() -> None:
    """经 loop 驱动（planner → astream）：重试成功后本轮正常结束。"""
    calls: list[int] = []

    def handler(**_kw: Any) -> str:
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("slow")
        return "ok"

    provider = ToolProvider()
    provider.register(_tool(handler=handler, reversible=True))
    result = _loop(provider, _chain(provider, max_attempts=2)).run("hi")

    assert len(calls) == 2  # noqa: PLR2004
    assert result.failed is False  # 工具失败不判轮失败（ReAct 自愈），重试成功后更不失败


def test_execution_failure_retries_then_succeeds() -> None:
    """执行异常（EXECUTION_FAILED）同样在可重试白名单内。"""
    calls: list[int] = []

    def handler(**_kw: Any) -> str:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return "ok"

    provider = ToolProvider()
    provider.register(_tool(handler=handler, reversible=True))
    result = _act(_loop(provider, _chain(provider, max_attempts=2)), "tools.flaky")

    assert len(calls) == 2  # noqa: PLR2004
    assert result.failed is False


def test_irreversible_tool_not_retried() -> None:
    """不可逆工具失败 ⇒ 不重试，首次失败结果原样透出（避免部分外写被放大）。"""
    calls: list[int] = []

    def handler(**_kw: Any) -> str:
        calls.append(1)
        raise TimeoutError("slow")

    provider = ToolProvider()
    provider.register(_tool(handler=handler, reversible=False))
    result = _act(_loop(provider, _chain(provider)), "tools.flaky")

    assert len(calls) == 1  # 不可逆 ⇒ 不重试
    assert result.failed is True
    assert result.error == "TIMEOUT"  # 失败码原样透出


def test_policy_denial_not_retried() -> None:
    """策略性拒绝（未知工具 / 参数校验失败）不重试。"""
    calls: list[int] = []

    def handler(**_kw: Any) -> str:
        calls.append(1)
        return "ok"

    provider = ToolProvider()
    provider.register(_tool(handler=handler, reversible=True))
    # 未知工具 ⇒ INVALID_ARGS（策略拒绝，不在白名单）；handler 从未被调用
    result = _act(_loop(provider, _chain(provider)), "tools.absent")

    assert calls == []
    assert result.failed is True
    assert result.error == "INVALID_ARGS"


def test_exhausted_returns_last_failure_as_is() -> None:
    """重试耗尽 ⇒ 原样返回最后一次失败结果（不改码、不降级）。"""
    calls: list[int] = []

    def handler(**_kw: Any) -> str:
        calls.append(1)
        raise RuntimeError("boom")

    provider = ToolProvider()
    provider.register(_tool(handler=handler, reversible=True))
    result = _act(_loop(provider, _chain(provider, max_attempts=3)), "tools.flaky")

    max_attempts = 3
    assert len(calls) == max_attempts  # 尝试次数上界（含首次）
    assert result.failed is True
    assert result.error == "EXECUTION_FAILED"  # 原样返回，不降级、不改码


def test_no_wrapper_calls_once_byte_identical() -> None:
    """缺省关（不包裹执行接缝）⇒ 一次工具动作只调用一次（无重试）。"""
    calls: list[int] = []

    def handler(**_kw: Any) -> str:
        calls.append(1)
        raise RuntimeError("boom")

    provider = ToolProvider()
    provider.register(_tool(handler=handler, reversible=True))
    result = _act(_loop(provider, None), "tools.flaky")

    assert len(calls) == 1
    assert result.failed is True


# ---- 配置三面 + 非法阻断 ----


def _write_config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path, extra: str = "", *, environ: dict[str, str] | None = None
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
    )
    manager.load()
    return manager


def test_spec_declares_retry_key() -> None:
    specs = {spec.key: spec for spec in config_specs()}
    assert "constraints.retry_attempts" in specs


def test_config_default_is_zero(tmp_path: Path) -> None:
    assert _manager(tmp_path).retry_attempts() == 0


def test_config_yaml_enables(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "constraints:\n  retry_attempts: 3\n")
    assert manager.retry_attempts() == 3  # noqa: PLR2004


def test_config_env_overrides(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "constraints:\n  retry_attempts: 2\n",
        environ={"CORE_CONSTRAINTS_RETRY_ATTEMPTS": "5"},
    )
    assert manager.retry_attempts() == 5  # noqa: PLR2004


@pytest.mark.parametrize("bad", [-1, True, "abc", 1.5])
def test_illegal_retry_value_blocks_startup(tmp_path: Path, bad: Any) -> None:
    yaml_bad = _write_config(tmp_path, f"constraints:\n  retry_attempts: {bad!r}\n")
    manager = ConfigManager(yaml_path=yaml_bad, environ={"OPENAI_API_KEY": "sk-test"})
    with pytest.raises(ConfigurationError):
        manager.load()


# ---- 组合根注入 ----


def _runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extra: str = "") -> Any:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path))
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, extra)))


def test_composition_default_off_leaves_act_unwrapped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """缺省 `retry_attempts=0` ⇒ 主 loop 执行接缝**未被包裹**（既有路径逐字不变）。

    `self._act is self.act`（绑定方法）⇒ `__func__` 即 `DefaultLoop.act` 本体。
    """
    runtime = _runtime(monkeypatch, tmp_path)
    assert getattr(runtime.loop._act, "__func__", None) is DefaultLoop.act  # noqa: SLF001


def test_composition_enabled_wraps_act(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`retry_attempts > 0` ⇒ 主 loop 执行接缝被 FaultChain 包裹（普通函数，无 `__func__`）。"""
    runtime = _runtime(monkeypatch, tmp_path, "constraints:\n  retry_attempts: 2\n")
    assert getattr(runtime.loop._act, "__func__", None) is not DefaultLoop.act  # noqa: SLF001
