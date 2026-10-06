"""神兽运行时接线测试（change 0057 / 账本 E3）。

证明规格 R4/R5 里此前 deferred 的三件事在生产装配真实可达：①20 枚神通进全局技能库；
②专属路由由**路由期作用域**强制（主 Agent 与他兽都看不到，非调用方自觉）；③生产召唤出的
神兽会话持有**按兽装配的真实 loop** 与共享记忆，`remember()` 落 ``source=beast.<id>``。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from core.beast import BeastRegistry, register_innate_skills
from core.beast.models import BeastSessionState
from core.configuration import ConfigManager
from core.llm_provider.models import LLMChunk
from core.loop import DefaultLoop
from core.memory import MemoryEntry
from core.runtime import build_runtime
from core.skills import Skill, SkillLibrary, SkillRouter

# 青龙的领域职责原文（= 其神通的 task_types[0]）——用作「本该命中」的路由任务
_QINGLONG_TASK = "架构设计 / 蓝图与骨架生成"


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
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def _library() -> SkillLibrary:
    """装好 20 枚神通的库（纯内存，不落盘）。"""
    library = SkillLibrary()
    register_innate_skills(library, BeastRegistry())
    return library


def _beast_entries(memory: Any) -> list[Any]:
    """共享记忆里 ``source`` 属于神兽命名空间的条目。"""
    return [e for e in memory.read("") if str(e.source).startswith("beast.")]


def _patch_llm(monkeypatch, runtime, reply: str) -> None:
    """把组合根 provider 的流式接口换成固定回复（离线端到端）。"""

    async def _astream(_request: Any):
        yield LLMChunk(content=reply)

    monkeypatch.setattr(runtime.llm, "astream", _astream)


# ---- 注册面 ----


def test_build_runtime_registers_innate_skills(runtime) -> None:
    """组合根把名册里每兽的独有神通都注册进全局技能库，字段符合 Skill 契约。"""
    registry = BeastRegistry()
    registered = {
        s.skill_id: s
        for s in runtime.skill_router._library.all_skills()  # noqa: SLF001 — 接线断言
        if s.skill_id.startswith("beast.")
    }
    assert sorted(registered) == sorted(b.innate_skill for b in registry.all())
    qinglong = registered["beast.qinglong.blueprint"]
    assert qinglong.status == "active"
    assert qinglong.preconditions == [] and qinglong.param_schema == {}
    assert qinglong.instructions


# ---- 专属路由作用域 ----


def test_main_agent_route_excludes_dedicated_skills() -> None:
    """主 Agent（domain=None）看不到任何专属神通——否则会灌进主 prompt。"""
    router = SkillRouter(_library())
    assert router.match(_QINGLONG_TASK) == []
    assert router.misses[-1] == _QINGLONG_TASK  # 未命中口径不变


def test_dedicated_routing_scoped_to_owner_domain() -> None:
    """专属神通仅归属域可路由；他兽域不可见。"""
    router = SkillRouter(_library())
    hits = router.match(_QINGLONG_TASK, domain="beast.qinglong")
    assert "beast.qinglong.blueprint" in [m.skill.skill_id for m in hits]
    # 他兽域：归属域不同的神通不进候选（词法噪声项（如 "/"）仍可能命中他兽技能，
    # 但那属于打分口径，不属于作用域——作用域只保证「非本域专属神通不可达」）
    other = [m.skill.skill_id for m in router.match(_QINGLONG_TASK, domain="beast.baihu")]
    assert "beast.qinglong.blueprint" not in other


def test_generic_skills_visible_in_every_domain() -> None:
    """作用域不误伤通用技能：带域与不带域都可见。"""
    library = _library()
    library.register(
        Skill(
            skill_id="generic.deploy",
            description="通用部署",
            task_types=["deploy"],
            preconditions=[],
            param_schema={},
            instructions="按通用流程部署",
            status="active",
        )
    )
    router = SkillRouter(library)
    assert [m.skill.skill_id for m in router.match("deploy", domain="beast.qinglong")] == [
        "generic.deploy"
    ]
    assert [m.skill.skill_id for m in router.match("deploy")] == ["generic.deploy"]


# ---- 注入面（组合根 → 会话） ----


def test_build_runtime_exposes_beast_surface(runtime) -> None:
    assert runtime.beast_manager is not None
    assert runtime.beast_activator is not None


def test_production_summon_injects_loop_and_memory(runtime, monkeypatch) -> None:
    """生产召唤出的会话持有按兽装配的 loop（非 echo 兜底）与共享记忆。"""
    _patch_llm(monkeypatch, runtime, "青龙已就位")
    session = asyncio.run(runtime.beast_activator.activate_from_cli("qinglong", ["设计架构"]))
    assert session.state is BeastSessionState.RECALLED  # 任务完成自动回归
    assert session.loop is not runtime.loop  # 独立实例
    assert getattr(session.loop, "_planner", None) is not None  # 非默认 echo loop
    assert session._memory is runtime.memory  # noqa: SLF001 — 注入生效断言


def test_end_to_end_summon_runs_real_loop_and_isolates_memory(runtime, monkeypatch) -> None:
    """端到端：真实 loop 跑完 → remember 落 beast.<id>，主记忆命名空间不混入。"""
    _patch_llm(monkeypatch, runtime, "青龙已完成蓝图设计")
    session = asyncio.run(runtime.beast_activator.activate_from_cli("qinglong", ["设计架构"]))
    assert session.last_result is not None and not session.last_result.failed

    entry = session.remember("青龙蓝图：分层装配")  # 记忆已注入（不再抛 BEAST_MEMORY_WRITE_FAILED）
    assert entry.source == "beast.qinglong"
    assert [e for e in runtime.memory.read("蓝图") if e.source == "beast.qinglong"]

    before = len(_beast_entries(runtime.memory))
    asyncio.run(runtime.loop.arun("普通任务"))
    assert len(_beast_entries(runtime.memory)) == before  # 主 Agent 不写神兽命名空间


def test_beast_loop_recalls_own_namespace_only(runtime, monkeypatch) -> None:
    """E54：兽的真实装配器放行**自身**命名空间（改前被主侧封存一并挡掉），他兽仍被排除。"""
    _patch_llm(monkeypatch, runtime, "青龙已完成蓝图设计")
    session = asyncio.run(runtime.beast_activator.activate_from_cli("qinglong", ["设计架构"]))

    for entry_id, source in (("q1", "beast.qinglong"), ("h1", "beast.baihu"), ("m1", "loop")):
        runtime.memory.write(
            "L2",
            MemoryEntry(
                id=entry_id,
                layer="L2",
                content=f"蓝图 {source} 产物",
                tags=[],
                source=source,
                trace_id=f"t-{entry_id}",
            ),
        )

    beast_loop = cast(DefaultLoop, session.loop)  # noqa: SLF001 — 真实装配器断言
    pack = beast_loop._planner._assembler.build(
        "蓝图", stage="reason", budget=4096, session_id="beast.qinglong"
    )
    sources = [str(f["source"]) for f in pack.facts]
    assert "beast.qinglong" in sources, "兽应能召回自身轨迹（改前被同一排除挡掉）"
    assert "beast.baihu" not in sources, "他兽命名空间不得进入该兽检索面"

    main_pack = runtime.loop._planner._assembler.build(  # noqa: SLF001 — 主侧封存不动
        "蓝图", stage="reason", budget=4096
    )
    assert not [f for f in main_pack.facts if str(f["source"]).startswith("beast.")], (
        "主 loop 封存语义逐字不动"
    )
