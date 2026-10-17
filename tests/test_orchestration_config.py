"""编排调度配置（change 0123 / phase-29 change C：E50）。

规格「编排调度配置」要求 `orchestration.difficulty_policy`（默认 `off`）与
`orchestration.max_concurrency`（默认 `4`）经 ConfigSpec 单一真源三面齐备、非法取值**校验期阻断**；
规格「难易度感知的调度策略」要求两项由**组合根**注入 `TaskScheduler`（`max_concurrency`
**不得**依赖构造缺省 —— 否则上限判据空转，与账本 E15 同型）。

本文件证明：三面一致与优先级链 / 缺省回落代码缺省（`off` / `4`）/ 非法取值阻断启动（不静默兜底）/
组合根**真的**把两值注入生产编排器。
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.entry import _key_to_patch
from core.orchestration import LLMTaskVerifier
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _manager(
    tmp_path: Path,
    extra: str = "",
    *,
    environ: dict[str, str] | None = None,
    cli: dict[str, object] | None = None,
    load: bool = True,
) -> ConfigManager:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    manager = ConfigManager(
        yaml_path=cfg,
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=cli,
    )
    if load:
        manager.load()
    return manager


# ---- ConfigSpec 单一真源面 ----


def test_specs_declare_orchestration_keys() -> None:
    specs = {spec.key: spec for spec in config_specs()}
    policy = specs["orchestration.difficulty_policy"]
    limit = specs["orchestration.max_concurrency"]
    assert (policy.cli_flag, policy.env_var, policy.map_to, policy.default) == (
        "--orchestration.difficulty-policy",
        "CORE_ORCHESTRATION_DIFFICULTY_POLICY",
        "orchestration.difficulty_policy",
        "off",
    )
    assert (limit.cli_flag, limit.env_var, limit.map_to, limit.default) == (
        "--orchestration.max-concurrency",
        "CORE_ORCHESTRATION_MAX_CONCURRENCY",
        "orchestration.max_concurrency",
        4,
    )
    timeout = specs["orchestration.subtask_timeout"]
    assert (timeout.cli_flag, timeout.env_var, timeout.map_to, timeout.default) == (
        "--orchestration.subtask-timeout",
        "CORE_ORCHESTRATION_SUBTASK_TIMEOUT",
        "orchestration.subtask_timeout",
        0,
    )


# ---- 缺省与三面 ----


def test_defaults_match_code_defaults(tmp_path: Path) -> None:
    """未配置 orchestration 段 ⇒ 回落代码缺省（`off` / 4），与引入前逐位一致。"""
    manager = _manager(tmp_path)
    assert manager.orchestration_difficulty_policy() == "off"
    assert manager.orchestration_max_concurrency() == 4  # noqa: PLR2004 — 即代码缺省
    assert manager.orchestration_subtask_timeout() == 0


def test_values_from_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "orchestration:\n"
        "  difficulty_policy: difficulty\n"
        "  max_concurrency: 2\n"
        "  subtask_timeout: 15\n",
    )
    assert manager.orchestration_difficulty_policy() == "difficulty"
    assert manager.orchestration_max_concurrency() == 2  # noqa: PLR2004 — 即 yaml 取值
    assert manager.orchestration_subtask_timeout() == 15  # noqa: PLR2004 — 即 yaml 取值


def test_env_overrides_yaml(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "orchestration:\n  max_concurrency: 2\n",
        environ={"CORE_ORCHESTRATION_MAX_CONCURRENCY": "3"},
    )
    assert manager.orchestration_max_concurrency() == 3  # noqa: PLR2004 — 即 env 取值


def test_cli_overrides_env_and_yaml(tmp_path: Path) -> None:
    """优先级链 CLI flag > env > config.yaml（配置能力的既有口径）。"""
    manager = _manager(
        tmp_path,
        "orchestration:\n  difficulty_policy: difficulty\n",
        environ={"CORE_ORCHESTRATION_DIFFICULTY_POLICY": "off"},
        cli={"orchestration.difficulty_policy": "difficulty"},
    )
    assert manager.orchestration_difficulty_policy() == "difficulty"


def test_orchestration_section_is_not_reported_unknown(tmp_path: Path) -> None:
    """ConfigSpec 声明段自动进白名单 ⇒ 不触发「未知配置段」告警（无第二真源）。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _manager(tmp_path, "orchestration:\n  max_concurrency: 2\n")
    assert [w for w in caught if "未知配置段" in str(w.message)] == []


# ---- 非法取值校验期阻断（不静默兜底） ----


@pytest.mark.parametrize("value", ["0", "-1", "2.5", "abc", "true"])
def test_invalid_max_concurrency_blocks_startup(tmp_path: Path, value: str) -> None:
    """并发上限须为 ≥1 的整数：0 / 负数 / 小数 / 非数值 / 布尔一律阻断启动。"""
    with pytest.raises(ConfigurationError, match="非法波次并发上限"):
        _manager(tmp_path, f"orchestration:\n  max_concurrency: {value}\n")


@pytest.mark.parametrize("value", ["-1", "2.5", "abc", "true"])
def test_invalid_subtask_timeout_blocks_startup(tmp_path: Path, value: str) -> None:
    """子任务超时须为 ≥0 的整数：负数 / 小数 / 非数值 / 布尔一律阻断启动。"""
    with pytest.raises(ConfigurationError, match="非法子任务超时"):
        _manager(tmp_path, f"orchestration:\n  subtask_timeout: {value}\n")


def test_env_subtask_timeout(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "orchestration:\n  subtask_timeout: 5\n",
        environ={"CORE_ORCHESTRATION_SUBTASK_TIMEOUT": "9"},
    )
    assert manager.orchestration_subtask_timeout() == 9  # noqa: PLR2004 — 即 env 取值


@pytest.mark.parametrize("value", ["fast", "parallel", "OFF", "1"])
def test_invalid_policy_blocks_startup(tmp_path: Path, value: str) -> None:
    """策略须为 `off` / `difficulty` 之一（拼错不得静默退化成缺省）。"""
    with pytest.raises(ConfigurationError, match="非法编排调度策略"):
        _manager(tmp_path, f"orchestration:\n  difficulty_policy: {value}\n")


# ---- 组合根注入（不得依赖构造缺省） ----


def test_build_runtime_injects_policy_and_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """组合根按配置值构造编排器（非构造缺省 `off` / 4）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(
        _manager(
            tmp_path,
            "orchestration:\n"
            "  difficulty_policy: difficulty\n"
            "  max_concurrency: 2\n"
            "  subtask_timeout: 7\n",
        )
    )
    # noqa: SLF001 — 接线断言（与 change 0115 的 loop 注入断言同型）
    assert runtime.orchestrator._difficulty_policy == "difficulty"  # noqa: SLF001
    assert runtime.orchestrator._max_concurrency == 2  # noqa: SLF001, PLR2004
    assert runtime.orchestrator._subtask_timeout == 7  # noqa: SLF001, PLR2004
    # 任务级判定器缺省注入（change 0248）：只生成标准不注入 checker ⇒ 生产任务全量 MISSING 失败
    assert isinstance(runtime.orchestrator._success_checker, LLMTaskVerifier)  # noqa: SLF001


def test_config_set_subtask_timeout_applies_and_persists(tmp_path: Path) -> None:
    """`config set orchestration.subtask_timeout` 真的生效并落盘（change 0247）。"""
    manager = _manager(tmp_path)
    assert manager.orchestration_subtask_timeout() == 0

    patch = _key_to_patch("orchestration.subtask_timeout", "30")
    manager.apply_change(patch)
    assert manager.orchestration_subtask_timeout() == 30  # noqa: PLR2004 — 即运行时取值

    manager.write_patch(patch)
    reloaded = ConfigManager(tmp_path / "config.yaml", environ={"OPENAI_API_KEY": "sk-test"})
    reloaded.load()
    assert reloaded.orchestration_subtask_timeout() == 30  # noqa: PLR2004 — 即落盘取值


def test_build_runtime_defaults_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 ⇒ 组合根注入代码缺省（`off` / 4）；仍走组合根，不落回构造缺省。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(_manager(tmp_path))
    assert runtime.orchestrator._difficulty_policy == "off"  # noqa: SLF001
    assert runtime.orchestrator._max_concurrency == 4  # noqa: SLF001, PLR2004
    assert runtime.orchestrator._subtask_timeout == 0  # noqa: SLF001
