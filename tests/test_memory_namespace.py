"""beast / pet 专属记忆命名空间接线测试（change 0110 / 账本 E37 + E38 + E39）。

证明规格里「已声明但未接线」的三件事在生产装配真实可达：
① 神兽轨迹以 ``source=beast.<agent_id>``（含 ``session_id`` 归组）落库，**主 loop 检索不命中**
（E37 + E38 封存）；② 神兽会话产物由**真实 loop** 写入而非会话 API 代笔；③ 宠物经**主人原话入口**
（激活 / 换活）观察偏好，``source=user`` 落共享 L2，``_preferences`` 非空 ⇒ ``surprise()`` 有产出
（E39）。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from core.beast.models import BeastSessionState
from core.configuration import ConfigManager
from core.context import DynamicAssembler
from core.llm_provider.models import LLMChunk
from core.loop import DefaultLoop, LoopPlugin, LoopResult
from core.memory import MemoryEntry, MemoryStore
from core.orchestration import AgentProfile, MultiAgentRouter, TaskHandoff
from core.pet.core import PetControl, PetSession, PetSessionState
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


def _sources(store: MemoryStore) -> set[str]:
    return {str(e.source) for e in store.audit()}


# ---- E37：source 注入面（单元） ----


def test_loop_writes_injected_source() -> None:
    """`DefaultLoop(source=…)` 的产物带注入的命名空间（神兽轨迹的落库口径）。"""
    store = MemoryStore()
    DefaultLoop(memory=store, source="beast.baihu").remember(
        "trace-beast", [{"round": 1, "ok": True, "error": None}, {"reply": "巡检完成"}]
    )
    assert _sources(store) == {"beast.baihu"}


def test_loop_source_defaults_to_loop() -> None:
    """红线：缺省 source 仍是 `"loop"`（主 Agent 语义向后兼容，逐字不变）。"""
    store = MemoryStore()
    DefaultLoop(memory=store).remember("trace-main", [{"reply": "主线结论"}])
    assert _sources(store) == {"loop"}


# ---- E37：read 侧排除（单元，含预算/强化口径） ----


def test_read_excludes_source_prefixes_but_default_is_unchanged() -> None:
    """排除参数只加不减：缺省调用仍返回神兽条目，显式排除则命中不到。"""
    store = MemoryStore()
    store.write("L2", _entry("b1", "蓝图 神兽产物", "beast.qinglong", "t1"))
    store.write("L2", _entry("m1", "蓝图 主线事实", "loop", "t2"))

    assert {e.id for e in store.read("蓝图")} == {"b1", "m1"}  # 缺省检索语义不变
    assert {e.id for e in store.read("蓝图", exclude_source_prefixes=("beast.",))} == {"m1"}


def test_excluded_entries_do_not_consume_budget_or_reinforce() -> None:
    """排除在排名/预算**之前**生效：被排除项不占预算、不被复用计数强化。"""
    store = MemoryStore()
    store.write("L2", _entry("b1", "蓝图 神兽产物", "beast.qinglong", "t1"))
    store.write("L2", _entry("m1", "蓝图 主线事实", "loop", "t2"))

    store.read("蓝图")  # 缺省调用 ⇒ 两条都被强化
    before = {e.id: e.reuse_count for e in store.audit()}
    store.read("蓝图", exclude_source_prefixes=("beast.",))
    after = {e.id: e.reuse_count for e in store.audit()}

    assert after["m1"] == before["m1"] + 1  # 命中项照常强化
    assert after["b1"] == before["b1"]  # 被排除项未被检索强化


def test_assembler_exclusion_is_opt_in() -> None:
    """装配器的排除是**显式开关**：缺省装配仍含神兽来源事实。"""
    store = MemoryStore()
    store.write("L2", _entry("b1", "蓝图 神兽产物", "beast.qinglong", "t1"))
    store.write("L2", _entry("m1", "蓝图 主线事实", "loop", "t2"))

    default = DynamicAssembler(memory=store)
    assert {f["source"] for f in default.build("蓝图", stage="reason", budget=4096).facts} == {
        "beast.qinglong",
        "loop",
    }
    scoped = DynamicAssembler(memory=store, exclude_source_prefixes=("beast.",))
    assert {f["source"] for f in scoped.build("蓝图", stage="reason", budget=4096).facts} == {
        "loop"
    }


# ---- E37：handoff 会话归组 ----


def test_task_handoff_session_id_is_backward_compatible() -> None:
    assert TaskHandoff(task="design").session_id == ""
    assert TaskHandoff(task="design", session_id="beast.qinglong").session_id == "beast.qinglong"


def test_handoff_forwards_session_id_to_sub_loop() -> None:
    """交接把 `session_id` 转交子 loop ⇒ 神兽条目按自身会话归组（不与主线未归组条目同组压实）。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store, source="beast.baihu")
    router = MultiAgentRouter([AgentProfile(agent_id="beast.baihu", loop=cast("LoopPlugin", loop))])

    result = asyncio.run(
        router.handoff("beast.baihu", TaskHandoff(task="巡检", session_id="beast.baihu"))
    )
    assert isinstance(result, LoopResult)

    entries = [e for e in store.audit() if e.source == "beast.baihu"]
    assert entries, "子 loop 应把本轮轨迹落库"
    assert {e.session_id for e in entries} == {"beast.baihu"}


# ---- E37 + E38：生产端到端（真实 loop 写入 / 主 loop 不命中） ----


def test_production_summon_writes_beast_namespace_through_real_loop(runtime, monkeypatch) -> None:
    """生产召唤 ⇒ 共享记忆出现 `source=beast.qinglong` 且带会话归组的条目（由 loop 写入）。"""
    _patch_llm(monkeypatch, runtime, "青龙已完成蓝图设计")
    session = asyncio.run(runtime.beast_activator.activate_from_cli("qinglong", ["设计架构"]))
    assert session.state is BeastSessionState.RECALLED

    entries = [e for e in runtime.memory.audit() if str(e.source).startswith("beast.")]
    assert entries, '神兽轨迹应以 beast.<agent_id> 落库（改前为 source="loop" 混入主记忆）'
    assert {str(e.source) for e in entries} == {"beast.qinglong"}
    assert {e.session_id for e in entries} == {"beast.qinglong"}


def test_main_loop_context_excludes_sealed_beast_partition(runtime, monkeypatch) -> None:
    """E38 封存：神兽自动回归后，**主 loop 上下文装配**不命中其分区，且不误伤主线事实。"""
    _patch_llm(monkeypatch, runtime, "青龙已完成蓝图设计")
    asyncio.run(runtime.beast_activator.activate_from_cli("qinglong", ["设计架构"]))
    runtime.memory.write("L2", _entry("main-1", "蓝图 主线事实", "loop", "t-main"))

    assembler = runtime.loop._planner._assembler  # noqa: SLF001 — 主 loop 的真实装配器
    pack = assembler.build("蓝图", stage="reason", budget=4096)

    sources = [f["source"] for f in pack.facts]
    assert "loop" in sources, "排除不误伤：主线事实仍应被装配"
    assert not [s for s in sources if s.startswith("beast.")], "封存的分区不得进主 loop 上下文"


# ---- E39：宠物偏好追踪（单元 + 端到端） ----


def test_observe_owner_is_fail_soft_without_memory() -> None:
    """无记忆后端（库层缺省用法）⇒ 静默跳过，入口不因偏好落库失败而失败。"""
    session = PetSession()
    assert session.observe_owner("editor: vim") is None
    assert session.prefer("editor") is None


def test_observe_owner_records_preference() -> None:
    store = MemoryStore()
    session = PetSession(memory=store)
    entry = session.observe_owner("editor: vim")
    assert entry is not None and entry.source == "user"
    assert session.prefer("editor") == "vim"
    assert [e.content for e in store.audit() if e.source == "user"] == ["editor: vim"]


def test_observe_owner_ignores_blank_text() -> None:
    store = MemoryStore()
    session = PetSession(memory=store)
    assert session.observe_owner("   ") is None
    assert [e for e in store.audit() if e.source == "user"] == []


def test_production_pet_activation_observes_owner_and_enables_surprise(
    runtime, monkeypatch
) -> None:
    """生产入口激活即观察主人原话 ⇒ 偏好落共享 L2、`prefer` 可用、`surprise()` 有真实产出。"""
    _patch_llm(monkeypatch, runtime, "已按你的偏好记下")
    session = runtime.pet_activator.activate_from_cli("gather", ["editor: vim"])
    assert session.state is PetSessionState.ACTIVE

    assert session.prefer("editor") == "vim"
    hits = [e for e in runtime.memory.read("editor") if e.source == "user"]
    assert hits, "偏好应以 source=user 落 runtime 共享 L2"

    surprise = session.surprise()
    assert surprise is not None, "有偏好 ⇒ 惊喜有真实 loop 产出（改前恒 None）"
    assert "editor=vim" in surprise


def test_pet_control_assign_observes_owner(runtime) -> None:
    """换一件活（控制面 `assign`）同样观察主人原话 —— 主人行为入口不止激活一处。"""
    session = runtime.pet_activator.activate_from_cli("gather", ["今日新闻"])
    PetControl(runtime.pet_manager).assign("theme: dark", session_id=session.session_id)
    assert session.prefer("theme") == "dark"


def test_slash_activation_does_not_fabricate_preference(runtime) -> None:
    """反例：`/pet` 斜杠入口无主人原话（goal 为合成文案）⇒ 零偏好写入（不谎报）。"""
    session = runtime.pet_activator.activate_from_slash("pet.gather")
    assert session._preferences == {}  # noqa: SLF001 — 反例断言
    assert [e for e in runtime.memory.audit() if e.source == "user"] == []


def test_cli_without_owner_text_does_not_observe(runtime) -> None:
    """反例：CLI 未给任务描述（goal 同样为合成文案）⇒ 零偏好写入。"""
    session = runtime.pet_activator.activate_from_cli("gather", [])
    assert session._preferences == {}  # noqa: SLF001 — 反例断言
    assert [e for e in runtime.memory.audit() if e.source == "user"] == []
