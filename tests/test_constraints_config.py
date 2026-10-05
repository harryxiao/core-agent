"""熔断阈值/冷却可配（change 0068 / 账本 E15）。

规格「容错中间件」要求熔断的失败阈值 N 与冷却期**可经配置覆盖**、非法取值**校验期阻断**。
本文件证明：`ConfigSpec` 单一真源三面（yaml / env / CLI）齐备且优先级链一致、缺省回落类默认
（5 次 / 30 秒）、非法取值阻断启动（**不静默兜底**），且组合根**真的**把配置值注入生产熔断链
（端到端：阈值设为 2 ⇒ 第 3 次调用即 `CIRCUIT_OPEN` 短路）。
"""

from __future__ import annotations

import warnings

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.loop import Action, ActionResult, LoopContext
from core.loop.constraints_adapter import ConstraintsChain
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)


def _write_config(tmp_path, constraints: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + constraints, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path,
    constraints: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
    load: bool = True,
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, constraints),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    if load:
        manager.load()
    return manager


# ---- ConfigSpec 单一真源面 ----


def test_specs_declare_circuit_breaker_keys() -> None:
    """两个键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备（单一真源）。"""
    specs = {spec.key: spec for spec in config_specs()}
    threshold = specs["constraints.failure_threshold"]
    cooldown = specs["constraints.cooldown_s"]
    assert threshold.cli_flag == "--constraints.failure-threshold"
    assert threshold.env_var == "CORE_CONSTRAINTS_FAILURE_THRESHOLD"
    assert threshold.map_to == "constraints.failure_threshold"
    assert (threshold.default, cooldown.default) == (5, 30.0)
    assert cooldown.cli_flag == "--constraints.cooldown-s"


# ---- 缺省与三面覆盖 + 优先级链 ----


def test_defaults_match_class_default(tmp_path) -> None:
    """未配置 constraints 段 ⇒ 回落类默认（5 / 30.0），与 change 0052 的行为逐位一致。"""
    manager = _manager(tmp_path)
    assert manager.circuit_breaker() == (5, 30.0)


def test_yaml_overrides_defaults(tmp_path) -> None:
    manager = _manager(tmp_path, "constraints:\n  failure_threshold: 2\n  cooldown_s: 10\n")
    assert manager.circuit_breaker() == (2, 10.0)


def test_env_overrides_yaml(tmp_path) -> None:
    """env（字符串）覆盖 yaml，取值按数值解析。"""
    manager = _manager(
        tmp_path,
        "constraints:\n  failure_threshold: 2\n",
        environ={"CORE_CONSTRAINTS_FAILURE_THRESHOLD": "3"},
    )
    assert manager.circuit_breaker() == (3, 30.0)


def test_cli_overrides_env_and_yaml(tmp_path) -> None:
    """优先级链 CLI flag > env > config.yaml（配置能力的既有口径）。"""
    manager = _manager(
        tmp_path,
        "constraints:\n  cooldown_s: 5\n",
        environ={"CORE_CONSTRAINTS_COOLDOWN_S": "10"},
        cli={"constraints.cooldown_s": "7"},
    )
    assert manager.circuit_breaker() == (5, 7.0)


# ---- 非法取值校验期阻断（不静默兜底） ----


@pytest.mark.parametrize("value", ["0", "-1", "abc", "2.5", "true"])
def test_invalid_threshold_blocks_startup(tmp_path, value: str) -> None:
    """阈值须为 ≥1 的整数：0 / 负数 / 非数值 / 小数 / 布尔一律阻断启动。"""
    yaml = f"constraints:\n  failure_threshold: {value}\n"
    with pytest.raises(ConfigurationError, match="非法熔断阈值"):
        _manager(tmp_path, yaml)


@pytest.mark.parametrize("value", ["-1", "-0.5", "soon"])
def test_invalid_cooldown_blocks_startup(tmp_path, value: str) -> None:
    """冷却须为 ≥0 的数值：负数 / 非数值阻断启动。"""
    yaml = f"constraints:\n  cooldown_s: {value}\n"
    with pytest.raises(ConfigurationError, match="非法熔断冷却"):
        _manager(tmp_path, yaml)


def test_invalid_value_does_not_silently_fall_back(tmp_path) -> None:
    """非法取值**不得**退化成缺省（否则配置错误会被掩盖成「看起来正常」）。"""
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, "constraints:\n  failure_threshold: 0\n")


# ---- 段名白名单（E18 单一真源：ConfigSpec 声明段自动进白名单） ----


def test_constraints_section_is_not_reported_unknown(tmp_path) -> None:
    """`constraints:` 已由 ConfigSpec 声明 ⇒ 不触发「未知配置段」告警。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager = _manager(tmp_path, "constraints:\n  failure_threshold: 2\n")
    assert [w for w in caught if "未知配置段" in str(w.message)] == []
    assert manager.circuit_breaker() == (2, 30.0)


# ---- 组合根注入 + 端到端 ----


@pytest.fixture
def state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _production_chain(runtime) -> ConstraintsChain:
    """取组合根注入主 loop 的 constraints 链（子 agent loop 共享同一实例）。"""
    return runtime.loop._middlewares[0].__self__  # noqa: SLF001 — 接线断言


def test_build_runtime_injects_configured_threshold(tmp_path, state_dir) -> None:
    """组合根按配置值构造熔断链（不再是写死的类默认）。"""
    runtime = build_runtime(
        ConfigManager(
            yaml_path=_write_config(
                tmp_path, "constraints:\n  failure_threshold: 2\n  cooldown_s: 10\n"
            )
        )
    )
    chain = _production_chain(runtime)
    assert (chain.failure_threshold, chain.cooldown_s) == (2, 10.0)


def test_configured_threshold_drives_production_breaker(tmp_path, state_dir) -> None:
    """端到端：配置阈值为 2 ⇒ 生产链上第 3 次调用即短路（配置真的生效，非纸面）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "constraints:\n  failure_threshold: 2\n"))
    )
    chain = _production_chain(runtime)
    ctx = LoopContext()
    action = Action(tool_id="tools.a", args={})
    assert not chain.middleware(ctx, action).is_terminal  # 阈值内放行
    for _ in range(2):
        chain.observe_result(ctx, action, ActionResult(failed=True, error="EXECUTION_FAILED"))
    opened = chain.middleware(ctx, action)
    assert opened is not None and opened.is_terminal
    assert "CIRCUIT_OPEN" in str(opened.args.get("reply", ""))
