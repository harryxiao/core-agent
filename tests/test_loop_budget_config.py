"""循环预算参数可配（change 0098）。

规格「错误与预算控制」要求单任务最大循环次数与 token 预算**可经配置链设定**，且 token 预算
**由模型上下文窗口派生**（`llm.context_window - loop.output_reserve`）；规格「LLM 提供商配置」
与「循环预算配置」要求新增三键经 ConfigSpec 单一真源三面齐备、非法取值**校验期阻断**。

本文件证明：三键三面一致、缺省回落代码缺省（10 / 65536，与变更前逐位一致）、派生边界正确、
非法取值与**窗口不敷预留**阻断启动（**不静默兜底** —— `token_budget <= 0` 的语义是「关闭
token 维度」，静默兜底会把配置错误变成「预算维度失效」），且组合根**真的**把派生值注入
生产 loop（端到端：`max_rounds` 派生为 3 ⇒ 第 3 轮即 `LOOP_LIMIT_EXCEEDED`）。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.entry import _key_to_patch
from core.loop import Action, DefaultLoop
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)


def _write_config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path,
    extra: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
    load: bool = True,
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    if load:
        manager.load()
    return manager


# ---- ConfigSpec 单一真源面 ----


def test_specs_declare_loop_and_context_window_keys() -> None:
    """三键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备（单一真源）。"""
    specs = {spec.key: spec for spec in config_specs()}
    window = specs["llm.context_window"]
    reserve = specs["loop.output_reserve"]
    rounds = specs["loop.max_rounds"]
    assert window.cli_flag == "--llm.context-window"
    assert window.env_var == "CORE_LLM_CONTEXT_WINDOW"
    assert window.map_to == "llm.context_window"
    assert window.default == 0
    assert (reserve.cli_flag, reserve.env_var, reserve.default) == (
        "--loop.output-reserve",
        "CORE_LOOP_OUTPUT_RESERVE",
        8192,
    )
    assert (rounds.cli_flag, rounds.env_var, rounds.default) == (
        "--loop.max-rounds",
        "CORE_LOOP_MAX_ROUNDS",
        10,
    )


# ---- 缺省与派生 ----


def test_defaults_match_code_defaults(tmp_path: Path) -> None:
    """未配置 loop 段与 context_window ⇒ 回落代码缺省（10 / 65536），与变更前逐位一致。"""
    manager = _manager(tmp_path)
    assert manager.loop_limits() == (10, 65536)


def test_budget_derived_from_context_window(tmp_path: Path) -> None:
    """配了窗口且预留取缺省 ⇒ token 预算 = 窗口 - 预留（规格给出的算例）。"""
    manager = _manager(
        tmp_path,
        "loop:\n  output_reserve: 8192\n",
        environ={"CORE_LLM_CONTEXT_WINDOW": "131072"},
    )
    assert manager.loop_limits() == (10, 131072 - 8192)


def test_no_window_means_no_derivation(tmp_path: Path) -> None:
    """未配窗口 ⇒ 不派生，即便配了预留也回落代码缺省 65536。"""
    manager = _manager(tmp_path, "loop:\n  output_reserve: 8192\n")
    assert manager.loop_limits() == (10, 65536)


def test_window_without_reserve_uses_default_reserve(tmp_path: Path) -> None:
    """只配窗口 ⇒ 预留取缺省 8192。"""
    manager = _manager(tmp_path, environ={"CORE_LLM_CONTEXT_WINDOW": "65536"})
    assert manager.loop_limits() == (10, 65536 - 8192)


def test_max_rounds_from_yaml(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "loop:\n  max_rounds: 3\n")
    assert manager.loop_limits() == (3, 65536)


# ---- 三面优先级链 ----


def test_env_overrides_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "loop:\n  output_reserve: 1024\n",
        environ={"CORE_LOOP_OUTPUT_RESERVE": "2048", "CORE_LLM_CONTEXT_WINDOW": "65536"},
    )
    assert manager.loop_limits() == (10, 65536 - 2048)


def test_cli_overrides_env_and_yaml(tmp_path: Path) -> None:
    """优先级链 CLI flag > env > config.yaml（配置能力的既有口径）。"""
    manager = _manager(
        tmp_path,
        "loop:\n  max_rounds: 5\n",
        environ={"CORE_LOOP_MAX_ROUNDS": "7"},
        cli={"loop.max_rounds": "9"},
    )
    assert manager.loop_limits() == (9, 65536)


# ---- 非法取值校验期阻断（不静默兜底） ----


@pytest.mark.parametrize("value", ["-1", "2.5", "abc", "true"])
def test_invalid_context_window_blocks_startup(tmp_path: Path, value: str) -> None:
    """窗口须为 0 或 ≥1 的整数：负数 / 小数 / 非数值 / 布尔一律阻断启动。"""
    yaml = f"llm:\n  context_window: {value}\n"
    with pytest.raises(ConfigurationError, match="非法上下文窗口"):
        _manager(tmp_path, yaml)


@pytest.mark.parametrize("value", ["-1", "2.5", "abc", "true"])
def test_invalid_output_reserve_blocks_startup(tmp_path: Path, value: str) -> None:
    """预留须为 ≥0 的整数。"""
    yaml = f"loop:\n  output_reserve: {value}\n"
    with pytest.raises(ConfigurationError, match="非法输出预留"):
        _manager(tmp_path, yaml)


@pytest.mark.parametrize("value", ["0", "-1", "abc", "true"])
def test_invalid_max_rounds_blocks_startup(tmp_path: Path, value: str) -> None:
    """轮数上限须为 ≥1 的整数：0 / 负数 / 非数值 / 布尔一律阻断启动。"""
    yaml = f"loop:\n  max_rounds: {value}\n"
    with pytest.raises(ConfigurationError, match="非法循环次数上限"):
        _manager(tmp_path, yaml)


def test_window_not_exceeding_reserve_blocks_startup(tmp_path: Path) -> None:
    """交叉校验：窗口不大于预留 ⇒ 派生结果非正 ⇒ 阻断（不得静默变成「关闭预算维度」）。"""
    with pytest.raises(ConfigurationError, match="不敷输出预留"):
        _manager(
            tmp_path,
            "loop:\n  output_reserve: 8192\n",
            environ={"CORE_LLM_CONTEXT_WINDOW": "4096"},
        )


def test_invalid_value_does_not_silently_fall_back(tmp_path: Path) -> None:
    """非法取值**不得**退化成缺省（否则配置错误会被掩盖成「看起来正常」）。"""
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, "loop:\n  max_rounds: 0\n")


# ---- 段名白名单（ConfigSpec 声明段自动进白名单） ----


def test_loop_section_is_not_reported_unknown(tmp_path: Path) -> None:
    """`loop:` 已由 ConfigSpec 声明 ⇒ 不触发「未知配置段」告警。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        manager = _manager(tmp_path, "loop:\n  max_rounds: 3\n")
    assert [w for w in caught if "未知配置段" in str(w.message)] == []
    assert manager.loop_limits() == (3, 65536)


# ---- config set 三面齐备（CLI 入口真的能改到 loop.*） ----


def test_config_set_loop_key_applies_and_persists(tmp_path: Path) -> None:
    """`config set loop.output_reserve` 真的生效并落盘（extra 段浅合并，不得静默丢弃）。"""
    manager = _manager(tmp_path, environ={"CORE_LLM_CONTEXT_WINDOW": "65536"})
    assert manager.loop_limits() == (10, 65536 - 8192)

    patch = _key_to_patch("loop.output_reserve", "4096")
    manager.apply_change(patch)
    assert manager.loop_limits() == (10, 65536 - 4096)

    manager.write_patch(patch)
    reloaded = ConfigManager(
        tmp_path / "config.yaml",
        environ={"OPENAI_API_KEY": "sk-test", "CORE_LLM_CONTEXT_WINDOW": "65536"},
    )
    reloaded.load()
    assert reloaded.loop_limits() == (10, 65536 - 4096)


def test_config_set_context_window_applies(tmp_path: Path) -> None:
    """`config set llm.context_window` 同样可达（结构化段）。"""
    manager = _manager(tmp_path)
    patch = _key_to_patch("llm.context_window", "65536")
    manager.apply_change(patch)
    assert manager.loop_limits() == (10, 65536 - 8192)


# ---- 组合根注入 + 端到端 ----


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _main_loop(runtime: object) -> DefaultLoop:
    """取组合根装配的主 loop（子 agent / 神兽 / 宠物 loop 同源同一对参数）。"""
    return cast(DefaultLoop, runtime.loop)  # type: ignore[attr-defined]


def test_build_runtime_injects_derived_limits(tmp_path: Path, state_dir: Path) -> None:
    """组合根按派生值构造主 loop（不再是写死的类默认）。"""
    runtime = build_runtime(
        ConfigManager(
            yaml_path=_write_config(tmp_path, "loop:\n  max_rounds: 3\n  output_reserve: 1024\n"),
            environ={"OPENAI_API_KEY": "sk-test", "CORE_LLM_CONTEXT_WINDOW": "65536"},
        )
    )
    loop = _main_loop(runtime)
    assert (loop._max_rounds, loop._token_budget) == (3, 65536 - 1024)  # noqa: SLF001 — 接线断言


def test_build_runtime_defaults_unchanged(tmp_path: Path, state_dir: Path) -> None:
    """未配置 ⇒ 组合根注入代码缺省（变更前后行为逐位一致）。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    loop = _main_loop(runtime)
    assert (loop._max_rounds, loop._token_budget) == (10, 65536)  # noqa: SLF001 — 接线断言


def test_configured_max_rounds_drives_production_loop(tmp_path: Path) -> None:
    """端到端：`loop_limits()` 派生为 3 ⇒ 真实 loop 第 3 轮即 `LOOP_LIMIT_EXCEEDED`。"""
    max_rounds, token_budget = _manager(tmp_path, "loop:\n  max_rounds: 3\n").loop_limits()
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        max_rounds=max_rounds,
        token_budget=token_budget,
    )
    result = loop.run("hi")
    assert "LOOP_LIMIT_EXCEEDED" in result.reply


# ---- 会话历史回灌轮数（change 0115）----

# 规格缺省：回灌最近 20 轮对话历史（configuration/spec.md「循环预算配置」）
_DEFAULT_HISTORY_TURNS = 20


def test_history_turns_spec_declared() -> None:
    """新键经 ConfigSpec 单一真源声明 ⇒ 三面齐备（不走 `loop_limits()` 元组）。"""
    spec = {spec.key: spec for spec in config_specs()}["loop.history_turns"]
    assert (spec.cli_flag, spec.env_var, spec.default) == (
        "--loop.history-turns",
        "CORE_LOOP_HISTORY_TURNS",
        _DEFAULT_HISTORY_TURNS,
    )


def test_history_turns_default(tmp_path: Path) -> None:
    assert _manager(tmp_path).history_turns() == _DEFAULT_HISTORY_TURNS


def test_history_turns_from_yaml(tmp_path: Path) -> None:
    turns = 3
    assert _manager(tmp_path, f"loop:\n  history_turns: {turns}\n").history_turns() == turns


def test_history_turns_env_overrides_yaml(tmp_path: Path) -> None:
    env_turns = 4
    manager = _manager(
        tmp_path,
        "loop:\n  history_turns: 3\n",
        environ={"CORE_LOOP_HISTORY_TURNS": str(env_turns)},
    )
    assert manager.history_turns() == env_turns


def test_history_turns_cli_overrides_env_and_yaml(tmp_path: Path) -> None:
    cli_turns = 5
    manager = _manager(
        tmp_path,
        "loop:\n  history_turns: 3\n",
        environ={"CORE_LOOP_HISTORY_TURNS": "4"},
        cli={"loop.history_turns": str(cli_turns)},
    )
    assert manager.history_turns() == cli_turns


def test_history_turns_zero_disables_replay(tmp_path: Path) -> None:
    """`0` 合法（关闭回灌）——与 `max_rounds` 的「须 ≥1」不同。"""
    assert _manager(tmp_path, "loop:\n  history_turns: 0\n").history_turns() == 0


@pytest.mark.parametrize("value", ["-1", "2.5", "abc", "true"])
def test_invalid_history_turns_blocks_startup(tmp_path: Path, value: str) -> None:
    """回灌轮数须为 ≥0 的整数：负数 / 小数 / 非数值 / 布尔一律阻断启动。"""
    with pytest.raises(ConfigurationError, match="非法回灌轮数"):
        _manager(tmp_path, f"loop:\n  history_turns: {value}\n")


def test_history_turns_keeps_loop_limits_arity(tmp_path: Path) -> None:
    """新键走**独立访问器** ⇒ `loop_limits()` 仍是 (max_rounds, token_budget) 二元组。"""
    assert _manager(tmp_path, "loop:\n  history_turns: 5\n").loop_limits() == (10, 65536)
