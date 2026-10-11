"""功能开关运行时门控（change 0067 / 账本 E10）。

规格「功能开关（feature flag）」要求「关闭的模块不加载、不初始化」。本文件证明组合根**真的**
按 `features.<模块>: false` 裁剪装配，且裁剪是**彻底**的：不构造实例、不注册装配期副作用
（技能注册 / 状态文件读取）、不接入口。同时证明**缺省即装配**（缺省 = 与门控落地前逐位一致）
与**两级开关互不覆盖**（`features.pet` 管装配、`pet.enabled` 管启用）。
"""

from __future__ import annotations

import pytest

from core.configuration import ConfigManager
from core.entry import main
from core.runtime import GATABLE_MODULES, KNOWN_FEATURE_MODULES, OPT_IN_MODULES, build_runtime

_QX_TASK = "架构设计 / 蓝图与骨架生成"  # 与 beast.qinglong 神通 task_types 词元重合（同 A7）
_QX_DOMAIN = "beast.qinglong"
_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)


def _write_config(tmp_path, *, flags: dict[str, bool] | None = None) -> str:
    body = _LLM_SECTION
    if flags:
        body += "features:\n" + "".join(
            f"  {name}: {'true' if value else 'false'}\n" for name, value in flags.items()
        )
    cfg = tmp_path / "config.yaml"
    cfg.write_text(body, encoding="utf-8")
    return str(cfg)


def _manager(tmp_path, sub: str, *, flags: dict[str, bool] | None = None) -> ConfigManager:
    """独立子目录里的 manager：同一用例要对比多份配置时避免共用同一文件。"""
    home = tmp_path / sub
    home.mkdir()
    manager = ConfigManager(yaml_path=_write_config(home, flags=flags))
    manager.load()
    return manager


@pytest.fixture
def state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _runtime(tmp_path, **flags: bool):
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, flags=flags or None)))


# ---- 缺省即装配（与门控落地前逐位一致） ----


def test_default_assembles_every_gatable_module(tmp_path, state_dir) -> None:
    """无 features 段 ⇒ 三模块照常装配（缺省开，兼容现状）。"""
    runtime = _runtime(tmp_path)
    assert runtime.pet_manager is not None
    assert runtime.pet_activator is not None
    assert runtime.beast_manager is not None
    assert runtime.beast_activator is not None
    assert runtime.evolution is not None
    assert runtime.loop._cold_path is not None  # noqa: SLF001 — 装配断言


def test_explicit_true_equals_default(tmp_path, state_dir) -> None:
    """显式 `true` 与未声明等价。"""
    runtime = _runtime(tmp_path, pet=True, beast=True, evolution=True)
    assert runtime.pet_manager is not None
    assert runtime.beast_manager is not None
    assert runtime.evolution is not None


def test_gating_whitelist_is_pet_beast_evolution() -> None:
    """门控名单是组合根单一真源（规格正文点名同一组）。"""
    assert set(GATABLE_MODULES) == {"pet", "beast", "evolution"}


# ---- 第二条极性：缺省关名单（change 0112） ----


def test_opt_in_whitelist_members() -> None:
    """缺省关名单同样是组合根单一真源（规格正文点名）。

    `evolution_benchmark_runner`（change 0212）：结晶通路的真实基准执行器 —— 与
    `evolution_executor` 同性质（能真实调用模型的执行面）⇒ 同极性（缺省关）。
    """
    assert set(OPT_IN_MODULES) == {"evolution_executor", "evolution_benchmark_runner"}


def test_two_polarities_are_carried_by_separate_lists() -> None:
    """两极性各由**独立**名单承载：同一个名字不会同时是「缺省开」与「缺省关」。"""
    assert set(OPT_IN_MODULES) & set(GATABLE_MODULES) == set()


def test_known_feature_modules_is_the_union() -> None:
    """已知模块名集合 = 两名单之**并**（供未知开关名告警，账本 E20①）。"""
    assert KNOWN_FEATURE_MODULES == GATABLE_MODULES + OPT_IN_MODULES
    assert set(KNOWN_FEATURE_MODULES) == set(GATABLE_MODULES) | set(OPT_IN_MODULES)


def test_opt_in_module_is_off_until_explicitly_true(monkeypatch, tmp_path) -> None:
    """缺省关：未声明 ⇒ 关；显式 `false` ⇒ 关；只有显式 `true` ⇒ 开（fail-closed）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    undeclared = _manager(tmp_path, "undeclared")
    off = _manager(tmp_path, "off", flags={"evolution_executor": False})
    on = _manager(tmp_path, "on", flags={"evolution_executor": True})

    assert undeclared.is_enabled("evolution_executor") is False
    assert undeclared.is_disabled("evolution_executor") is False  # 缺省关 ≠ 缺省装配名单
    assert off.is_enabled("evolution_executor") is False
    assert on.is_enabled("evolution_executor") is True


# ---- 关闭 ⇒ 装配面为空、装配期副作用不发生 ----


def test_disabled_pet_has_empty_surface_and_skips_registry(tmp_path, state_dir) -> None:
    """pet 关闭：不构造 PetManager/PetActivator，**不读** 注册表（损坏的 pets.json 也不触发）。"""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "pets.json").write_text("{ 这不是合法 JSON", encoding="utf-8")

    runtime = _runtime(tmp_path, pet=False)

    assert runtime.pet_manager is None
    assert runtime.pet_activator is None


def test_registry_read_is_live_probe_for_the_disabled_case(tmp_path, state_dir) -> None:
    """上例的探针非空转：**缺省**装配会真读注册表 ⇒ 损坏文件必然炸（对照组）。"""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "pets.json").write_text("{ 这不是合法 JSON", encoding="utf-8")

    with pytest.raises(ValueError):  # json.JSONDecodeError ⊂ ValueError
        _runtime(tmp_path)


def test_disabled_beast_does_not_register_innate_skills(tmp_path, state_dir) -> None:
    """beast 关闭：不构造 manager/activator，且 20 神通**不进**全局技能库。"""
    runtime = _runtime(tmp_path, beast=False)

    assert runtime.beast_manager is None
    assert runtime.beast_activator is None
    assert runtime.skill_router.match(_QX_TASK, domain=_QX_DOMAIN, top_k=10) == []


def test_innate_skills_are_registered_by_default(tmp_path, state_dir) -> None:
    """对照组：缺省装配时域内路由能命中神通（证明上例的「空」是真裁剪）。"""
    runtime = _runtime(tmp_path)
    hits = runtime.skill_router.match(_QX_TASK, domain=_QX_DOMAIN, top_k=10)
    assert any(m.skill.skill_id.startswith("beast.") for m in hits)


def test_disabled_evolution_drops_cold_path(tmp_path, state_dir) -> None:
    """evolution 关闭：不构造引擎/worker，loop 冷路径随之置 None（不造假空转闭包）。"""
    runtime = _runtime(tmp_path, evolution=False)

    assert runtime.evolution is None
    assert runtime.loop._cold_path is None  # noqa: SLF001 — 装配断言


def test_core_surface_survives_all_modules_disabled(tmp_path, state_dir) -> None:
    """三模块全关：核心面（循环 / 记忆 / 工具 / 技能路由 / 编排）照常装配。"""
    runtime = _runtime(tmp_path, pet=False, beast=False, evolution=False)

    assert runtime.loop is not None
    assert runtime.memory is not None
    assert runtime.tools is not None
    assert runtime.skill_router is not None
    assert runtime.orchestrator is not None


# ---- 谓词口径 ----


def test_is_disabled_polarity(monkeypatch, tmp_path) -> None:
    """`is_disabled` 缺省不关：只有显式 false 为真（true 与未声明都不关）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    undeclared = _manager(tmp_path, "undeclared")
    doubled = _manager(tmp_path, "doubled", flags={"pet": True})
    off = _manager(tmp_path, "off", flags={"pet": False})

    assert undeclared.is_disabled("pet") is False
    assert doubled.is_disabled("pet") is False
    assert off.is_disabled("pet") is True


def test_is_enabled_semantics_unchanged(monkeypatch, tmp_path) -> None:
    """`is_enabled`（显式开启查询，缺省 false）语义不变 —— 缺省装配名单仍用 `is_disabled`，
    缺省关名单（`OPT_IN_MODULES`）以本谓词作装配判据（见本文件第二条极性一节）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    undeclared = _manager(tmp_path, "undeclared")
    on = _manager(tmp_path, "on", flags={"pet": True})

    assert undeclared.is_enabled("pet") is False
    assert on.is_enabled("pet") is True


# ---- CLI 入口：关闭时统一拒绝（stderr 说明 + 退出 0，对齐 pet.enabled 未启用形态） ----

# (全局 flag, 子命令 argv, 被关闭的模块)：全局 flag 在前（argparse 全局面在子命令之前）。
_REFUSALS = [
    (["--pet-enabled"], ["pet", "list"], "pet"),
    ([], ["summon", "qinglong", "设计架构"], "beast"),
    ([], ["recall", "qinglong"], "beast"),
    ([], ["evolve", "run"], "evolution"),
    ([], ["evolve", "pending"], "evolution"),
    ([], ["evolve", "confirm", "abc123"], "evolution"),
    ([], ["evolve", "reject", "abc123"], "evolution"),
    ([], ["evolve", "implement", "abc123"], "evolution_executor"),
]


@pytest.mark.parametrize("case", _REFUSALS, ids=lambda c: c[2])
def test_cli_refuses_disabled_module(
    monkeypatch,
    tmp_path,
    capsys: pytest.CaptureFixture[str],
    case: tuple[list[str], list[str], str],
) -> None:
    """模块被关闭时七个入口一律：stderr 说明模块名 + 退出码 0（不装配、不报错退出）。

    pet 一条另加 `--pet-enabled`：无此 flag 时先撞上**二级开关**（pet.enabled 缺省关）——
    两级开关各报各的，正是规格场景「feature flag 不改变模块自身启用开关」。
    """
    globals_, argv, module = case
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    cfg = _write_config(tmp_path, flags={module: False})

    assert main(["--config", cfg, *globals_, *argv]) == 0
    captured = capsys.readouterr()
    assert module in captured.err
    assert "已关闭" in captured.err
    assert captured.out == ""
