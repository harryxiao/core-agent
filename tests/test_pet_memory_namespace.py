"""宠物记忆独立命名空间（change 0118 / phase-30 §8-A）。

证明三件事：① 宠物经**专属 loop** 产生的轨迹以 ``source=pet`` 落库，与主 Agent（``source=loop``）、
神兽（``source=beast.<agent_id>``）三者互不混同；② 主 Agent 检索面**封存** ``pet`` 命名空间
（**未带会话标识**、会话面不过滤时亦不吸收 —— 这正是改前的泄漏路径）；③ 封存不使宠物读不到
**自身**轨迹（排除面内放行自身命名空间），且主人偏好（``source=user``）不受影响。
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from core.configuration import ConfigManager
from core.context import DynamicAssembler
from core.llm_provider.models import LLMChunk
from core.loop import DefaultLoop
from core.memory import MemoryEntry, MemoryStore
from core.pet.core import PetSessionState
from core.runtime import build_runtime

# ---- 夹具 ----


def _write_config(tmp_path: Any) -> str:
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


def _patch_llm(monkeypatch, runtime, reply: str) -> None:
    """把组合根 provider 的流式接口换成固定回复（离线端到端）。"""

    async def _astream(_request: Any):
        yield LLMChunk(content=reply)

    monkeypatch.setattr(runtime.llm, "astream", _astream)


def _entry(entry_id: str, content: str, source: str, trace_id: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id, layer="L2", content=content, tags=[], source=source, trace_id=trace_id
    )


def _sources(entries: list[dict[str, str]]) -> set[str]:
    return {str(f["source"]) for f in entries}


# ---- 单元：读侧封存与放行（与 phase-26 E37 / change 0117 E54 同一机制） ----


def test_read_seals_pet_namespace_for_main() -> None:
    """排除面加 `pet`：宠物轨迹对主侧检索面不可见，缺省检索语义逐字不变。"""
    store = MemoryStore()
    store.write("L2", _entry("p1", "蓝图 宠物产物", "pet", "t1"))
    store.write("L2", _entry("m1", "蓝图 主线事实", "loop", "t2"))

    assert {e.id for e in store.read("蓝图")} == {"p1", "m1"}  # 缺省调用语义不变
    assert {e.id for e in store.read("蓝图", exclude_source_prefixes=("beast.", "pet"))} == {"m1"}


def test_pet_assembler_allows_own_namespace_only() -> None:
    """派生装配器（放行 `pet`）：宠物召回自身轨迹；神兽命名空间仍被排除；主线不受影响。"""
    store = MemoryStore()
    for entry_id, source in (("p1", "pet"), ("q1", "beast.qinglong"), ("m1", "loop")):
        store.write("L2", _entry(entry_id, f"蓝图 {source} 产物", source, f"t-{entry_id}"))

    sealed = DynamicAssembler(memory=store, exclude_source_prefixes=("beast.", "pet"))
    assert _sources(sealed.build("蓝图", stage="reason", budget=4096).facts) == {"loop"}

    pet = sealed.with_allow_source_prefixes("pet")
    assert _sources(pet.build("蓝图", stage="reason", budget=4096).facts) == {"pet", "loop"}
    assert sealed.build("蓝图", stage="reason", budget=4096).facts  # 原装配器逐字不动


def test_user_preference_survives_pet_sealing() -> None:
    """主人偏好（`source=user`）是刻意知识 ⇒ 封存 `pet` 不得连带挡掉它。"""
    store = MemoryStore()
    store.write("L2", _entry("u1", "editor 偏好 vim", "user", "t1"))
    store.write("L2", _entry("p1", "editor 宠物探索所得", "pet", "t2"))

    sealed = DynamicAssembler(memory=store, exclude_source_prefixes=("beast.", "pet"))
    assert _sources(sealed.build("editor", stage="reason", budget=4096).facts) == {"user"}


# ---- 生产端到端：宠物轨迹落 pet 命名空间 ----


def test_production_pet_trajectory_lands_in_pet_namespace(runtime, monkeypatch) -> None:
    """唤醒跑完一轮自治任务 ⇒ 共享记忆出现 `source=pet` + 宠物会话归属的条目。"""
    _patch_llm(monkeypatch, runtime, "已收集今日要闻")
    session = runtime.pet_activator.activate_from_cli("gather", ["今日新闻"])
    assert session.state is PetSessionState.ACTIVE
    session.wake()

    entries = [e for e in runtime.memory.audit() if str(e.source).startswith("pet")]
    assert entries, '宠物轨迹应以 source=pet 落库（改前为 source="loop" 混入主命名空间）'
    assert {str(e.source) for e in entries} == {"pet"}
    assert {e.session_id for e in entries} == {session.session_id}  # 双维度：命名空间 + 会话个体


def test_main_loop_context_seals_pet_partition(runtime, monkeypatch) -> None:
    """**未带会话标识**（会话面不过滤）时，主 loop 上下文仍不吸收宠物自治所得 —— 改前的泄漏路径。"""
    _patch_llm(monkeypatch, runtime, "已收集今日要闻")
    session = runtime.pet_activator.activate_from_cli("gather", ["今日新闻"])
    session.wake()
    runtime.memory.write("L2", _entry("main-1", "今日新闻 主线事实", "loop", "t-main"))

    assembler = runtime.loop._planner._assembler  # noqa: SLF001 — 主 loop 的真实装配器
    facts = assembler.build("今日新闻", stage="reason", budget=4096).facts
    sources = _sources(facts)

    assert "loop" in sources, "排除不误伤：主线事实仍应被装配"
    assert "pet" not in sources, "宠物命名空间不得被主 Agent 吸收为自身事实"
    # 内容级守门（改前宠物轨迹以 source="loop" 落库 ⇒ 真被主 Agent 当自身事实吸收）
    assert not [f for f in facts if "已收集今日要闻" in str(f["content"])]


def test_pet_loop_recalls_own_namespace_only(runtime, monkeypatch) -> None:
    """宠物的真实装配器放行**自身**命名空间（封存不得使宠物失忆）；神兽命名空间仍被排除。"""
    _patch_llm(monkeypatch, runtime, "已收集今日要闻")
    session = runtime.pet_activator.activate_from_cli("gather", ["今日新闻"])
    for entry_id, source in (("p1", "pet"), ("q1", "beast.qinglong"), ("m1", "loop")):
        runtime.memory.write(
            "L2", _entry(entry_id, f"今日新闻 {source} 产物", source, f"t-{entry_id}")
        )

    pet_loop = cast(DefaultLoop, session._loop)  # noqa: SLF001 — 真实装配器断言
    pack = pet_loop._planner._assembler.build(  # noqa: SLF001
        "今日新闻", stage="reason", budget=4096, session_id=session.session_id
    )
    sources = _sources(pack.facts)

    assert "pet" in sources, "宠物应能召回自身轨迹（封存须在排除面内放行自身命名空间）"
    assert "beast.qinglong" not in sources, "神兽命名空间不得进入宠物检索面"


def test_pet_sealing_does_not_relax_beast_sealing(runtime) -> None:
    """红线：排除面新增 `pet` 不得放宽 `beast.` 封存（phase-26 E37/E38/E39）。"""
    runtime.memory.write("L2", _entry("b1", "蓝图 神兽产物", "beast.qinglong", "t1"))
    runtime.memory.write("L2", _entry("p1", "蓝图 宠物产物", "pet", "t2"))

    pack = runtime.loop._planner._assembler.build(  # noqa: SLF001 — 主侧封存断言
        "蓝图", stage="reason", budget=4096
    )
    sources = _sources(pack.facts)
    assert not [s for s in sources if s.startswith("beast.")], "神兽封存语义逐字不动"
    assert "pet" not in sources
