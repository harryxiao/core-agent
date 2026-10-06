"""原生执行器的**装配裁剪**（change 0112 / DS1-a）：缺省不装配，显式 `true` 才装配。

规格 configuration「功能开关（feature flag）」第二条极性（缺省关）：`features.evolution_executor`
**未声明即视为关闭** —— 关时不构造实例、不产生装配期副作用；`crystallize` 的结局逐字回到现状。
门禁命令取自**单一真源** `GATE_COMMANDS`（执行器不得自选）。
"""

from __future__ import annotations

import warnings

from core.ci_cd import GATE_COMMANDS
from core.configuration import ConfigManager
from core.evolution import GenerationCandidate
from core.evolution.executor import EvolutionExecutor
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _write_config(tmp_path, *, executor_flag: bool | None) -> str:
    body = _LLM_SECTION
    if executor_flag is not None:
        body += f"features:\n  evolution_executor: {'true' if executor_flag else 'false'}\n"
    cfg = tmp_path / "config.yaml"
    cfg.write_text(body, encoding="utf-8")
    return str(cfg)


def _runtime(tmp_path, *, executor_flag: bool | None):
    return build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, executor_flag=executor_flag))
    )


def test_default_does_not_assemble_executor(tmp_path, monkeypatch) -> None:
    """缺省（未声明）⇒ 执行器不装配；evolution 本体照旧装配（逐字回到现状）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))

    runtime = _runtime(tmp_path, executor_flag=None)

    assert runtime.evolution_executor is None
    assert runtime.evolution is not None
    assert runtime.loop is not None


def test_explicit_true_assembles_executor(tmp_path, monkeypatch) -> None:
    """显式 `true` ⇒ 装配，且门禁名单来自单一真源 `GATE_COMMANDS`。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))

    runtime = _runtime(tmp_path, executor_flag=True)

    assert isinstance(runtime.evolution_executor, EvolutionExecutor)
    assert runtime.evolution_executor.gates == tuple(GATE_COMMANDS)


def test_explicit_false_does_not_assemble_executor(tmp_path, monkeypatch) -> None:
    """显式 `false` 与未声明同效（缺省关）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))

    runtime = _runtime(tmp_path, executor_flag=False)

    assert runtime.evolution_executor is None


def test_executor_writes_into_the_engines_ledger_file(tmp_path, monkeypatch) -> None:
    """制品落**既有候选台账文件**：另起一份装配仍查得到（「跨进程可查」的实现前提）。

    台账若被拆成两个库，本用例即红 —— 制品会只活在一次 CLI 进程里（复核无从谈起）。
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    candidate = GenerationCandidate(
        generation=1,
        target_plugin="loop.default",
        delta={"issue": "×"},
        kind="plugin",
        status="confirmed",
        risk_level="high",
    )

    runtime = _runtime(tmp_path, executor_flag=True)
    runtime.evolution_executor.queue.record(candidate)

    fresh = _runtime(tmp_path, executor_flag=True)
    assert fresh.evolution is not None
    assert fresh.evolution.engine.find(candidate.candidate_id) is not None


def test_executor_flag_is_a_known_feature_name(tmp_path, monkeypatch) -> None:
    """`evolution_executor` 属**已知模块名集合** ⇒ 不产生「未知功能开关」告警（账本 E20①）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _runtime(tmp_path, executor_flag=True)

    assert [str(w.message) for w in caught if "未知功能开关" in str(w.message)] == []


def test_executor_is_not_exposed_on_the_agent_tool_face(tmp_path, monkeypatch) -> None:
    """规格明写：执行器 SHALL NOT 注册为**任何 Agent 可调用的工具**（自改代码不经模型手）。

    对照组 `tools.gate_run`（S1）在场 ⇒ 断言非空转（工具面确实被枚举到了）。
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))

    runtime = _runtime(tmp_path, executor_flag=True)

    assert runtime.evolution_executor is not None
    ids = {d.tool_id for d in runtime.tools.active_tools()}
    assert "tools.gate_run" in ids
    assert [tid for tid in ids if "implement" in tid or "evolution" in tid] == []
