"""按会话隔离记忆（change 0114 / phase-28 E47）。

证明「会话之间对话内容严格隔离」在生产链路上真实成立：**读侧** `MemoryStore.read` 按会话过滤
（非空标识只返回「本会话 + 全局层」，空标识不过滤、语义逐字兼容）；**写入侧**各处执行轨迹按
发起会话归属（主 loop 落库、压实产物、路由未命中、宠物轨迹、编排子任务）；**刻意知识**
（`notes` 笔记层）显式留全局层，不参与隔离。
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager
from core.context import Compactor, DynamicAssembler
from core.llm_provider import LLMProvider
from core.loop import Action, DefaultLoop, LoopContext, LoopEvent, LoopPlugin, LoopResult
from core.loop.planner import LLMPlanner
from core.memory import MemoryEntry, MemoryStore
from core.notes import NoteEntry, NoteStore, promote_session_summary
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskScheduler,
)
from core.pet.core import PetSession, PetTask, PetTaskKind
from core.runtime import build_runtime
from core.skills import SkillLibrary, SkillRouter

# ---- 夹具 / 辅助 ----


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


def _entry(
    entry_id: str,
    content: str,
    *,
    source: str = "loop",
    session_id: str = "",
    trace_id: str = "t",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source=source,
        trace_id=trace_id,
        session_id=session_id,
    )


def _three() -> MemoryStore:
    """A / B / 未归属三组条目共用一个店（内容同 query，便于可见性对照）。"""
    store = MemoryStore()
    store.write("L2", _entry("a1", "部署方案 甲", session_id="A"))
    store.write("L2", _entry("b1", "部署方案 乙", session_id="B"))
    store.write("L2", _entry("g1", "部署方案 全局", session_id=""))
    return store


async def _drain(events: AsyncIterator[LoopEvent]) -> list[LoopEvent]:
    return [event async for event in events]


# ---- 读侧：会话可见性 ----


def test_read_scopes_to_session_plus_global_layer() -> None:
    """非空标识只返回「本会话条目 + 全局层（未归属）」——不越界、不遗漏全局。"""
    store = _three()
    assert {e.id for e in store.read("部署方案", session_id="A")} == {"a1", "g1"}


def test_other_session_facts_are_invisible() -> None:
    """反例守门：A 会话沉淀的事实绝不出现在 B 会话的检索结果中。"""
    store = _three()
    assert "a1" not in {e.id for e in store.read("部署方案", session_id="B")}


def test_blank_session_id_does_not_filter() -> None:
    """空标识 = 未归属调用者 ⇒ 不施加会话过滤（与既往逐字一致，fail-open）。"""
    store = _three()
    assert {e.id for e in store.read("部署方案")} == {"a1", "b1", "g1"}
    assert {e.id for e in store.read("部署方案", session_id="")} == {"a1", "b1", "g1"}


def test_session_filter_precedes_budget_and_reinforcement() -> None:
    """会话过滤在排名/预算**之前**：被滤项不占预算、不被复用计数强化。"""
    store = MemoryStore()
    store.write("L2", _entry("a1", "部署方案 " * 40, session_id="A"))
    store.write("L2", _entry("b1", "部署方案 " * 40, session_id="B"))

    store.read("部署方案")  # 缺省调用 ⇒ 两条都被强化
    before = {e.id: e.reuse_count for e in store.audit()}
    hits = store.read("部署方案", budget=1, session_id="A")
    after = {e.id: e.reuse_count for e in store.audit()}

    assert [e.id for e in hits] == ["a1"], "B 的条目被滤除 ⇒ 不吃 A 会话的预算"
    assert after["a1"] == before["a1"] + 1  # 命中项照常强化
    assert after["b1"] == before["b1"]  # 被滤项未被检索强化


def test_session_filter_composes_with_source_exclusion() -> None:
    """会话过滤与来源前缀排除同一口径、可叠加（两个条件同时生效）。"""
    store = MemoryStore()
    store.write("L2", _entry("a1", "部署方案 主线", source="loop", session_id="A"))
    store.write("L2", _entry("a2", "部署方案 神兽", source="beast.qinglong", session_id="A"))
    store.write("L2", _entry("b1", "部署方案 乙会话", session_id="B"))

    hits = store.read("部署方案", session_id="A", exclude_source_prefixes=("beast.",))
    assert {e.id for e in hits} == {"a1"}


# ---- 读侧：端到端（真装配器 / 真 loop） ----


class _RecordingStore:
    """记录 `read` 实参的替身：钉住「透传了什么」与「缺省调用形态未变」。"""

    def __init__(self) -> None:
        self.reads: list[dict[str, Any]] = []

    def read(self, query: str, budget: int = 4096, **kwargs: Any) -> list[MemoryEntry]:
        self.reads.append({"query": query, "budget": budget, **kwargs})
        return []


def test_assembler_forwards_session_id_only_when_present() -> None:
    """装配器把会话标识透传至 L2 检索；空标识 ⇒ 调用形态与既往**逐字一致**（两参 read）。"""
    spy = _RecordingStore()
    assembler = DynamicAssembler(memory=cast("MemoryStore", spy))
    assembler.build("蓝图", stage="reason", budget=100, session_id="A")
    assembler.build("蓝图", stage="reason", budget=100)

    assert spy.reads[0]["session_id"] == "A"
    assert "session_id" not in spy.reads[1]


def test_prompt_from_one_session_never_reaches_another(runtime) -> None:
    """端到端反向守门：A 会话沉淀的事实进 A 的 system prompt，**不进** B 的。"""
    runtime.memory.write("L2", _entry("a1", "部署方案 用蓝绿发布", session_id="A"))
    loop = runtime.loop
    planner = loop._planner  # noqa: SLF001 — 主 loop 的真实规划器/装配器
    prompt_a = planner._system_prompt(loop.perceive("部署方案", session_id="A"))  # noqa: SLF001
    prompt_b = planner._system_prompt(loop.perceive("部署方案", session_id="B"))  # noqa: SLF001

    assert "蓝绿发布" in prompt_a
    assert "蓝绿发布" not in prompt_b


def test_loop_threads_session_id_onto_context() -> None:
    """`astream(session_id=…)` 把标识落到上下文包；缺省调用面（一参 perceive）不变。"""
    seen: list[str] = []

    def planner(ctx: LoopContext) -> Action:
        seen.append(ctx.session_id)
        return Action(args={"reply": "ok"})

    loop = DefaultLoop(planner=planner)
    asyncio.run(_drain(loop.astream("任务", session_id="A")))

    assert seen == ["A"]
    assert loop.perceive("任务").session_id == ""


# ---- 推理期：技能路由（未命中记录归属） ----


def test_planner_skill_hint_call_shape_is_backward_compatible() -> None:
    """空标识 ⇒ 技能路由仍是**一参**调用（既有 1 参 lambda 替身不被逼改签名）。"""
    seen: list[str] = []
    planner = LLMPlanner(
        cast("LLMProvider", None), skill_router=lambda task: seen.append(task) or []
    )
    planner._skill_hints("任务一")  # noqa: SLF001
    assert seen == ["任务一"]


def test_planner_forwards_session_to_skill_router_when_present() -> None:
    """非空标识 ⇒ 透传至技能路由（会话成为归属维度，不只用于记忆写入）。"""
    calls: list[tuple[str, str]] = []

    def hook(task: str, session_id: str = "") -> list[dict[str, str]]:
        calls.append((task, session_id))
        return []

    planner = LLMPlanner(cast("LLMProvider", None), skill_router=hook)
    planner._skill_hints("任务二", "A")  # noqa: SLF001

    assert calls == [("任务二", "A")]


def test_router_miss_record_is_session_scoped() -> None:
    """路由未命中记录按调用方会话归属：他会话检索不到，不再成为全局可见条目。"""
    store = MemoryStore()
    router = SkillRouter(SkillLibrary(), memory=store)
    assert router.match("无人认领的独特任务", session_id="A") == []

    entries = [e for e in store.audit() if e.source == "skills"]
    assert {e.session_id for e in entries} == {"A"}
    assert all(e.id.startswith("skills.miss.A.") for e in entries)  # 会话键在 id 内（0117）
    assert store.read("无人认领", session_id="B") == []


def test_router_miss_defaults_to_default_key() -> None:
    """空标识 ⇒ 归缺省键 + 未归属（旧调用形态的结果逐字不变）。"""
    store = MemoryStore()
    router = SkillRouter(SkillLibrary(), memory=store)
    router.match("无人认领的独特任务")

    entries = [e for e in store.audit() if e.source == "skills"]
    assert all(e.id.startswith("skills.miss.default.") for e in entries)
    assert {e.session_id for e in entries} == {""}


# ---- 写入侧：压实产物归属 ----


def test_compactor_persist_attributes_session() -> None:
    """压实产物以本轮会话归属，且 id 带会话键（消跨会话覆盖）。"""
    store = MemoryStore()
    compactor = Compactor(memory=store)
    compaction = compactor.compact([{"id": "h1", "content": "结论：部署完成"}])
    compactor.persist(compaction, session_id="s1")

    entries = [e for e in store.audit() if e.source == "context"]
    assert {e.session_id for e in entries} == {"s1"}
    assert {e.id for e in entries} == {"compaction.fact.s1.0"}


def test_compactor_persist_defaults_to_default_key() -> None:
    """空标识 ⇒ 归缺省键（沿用 store 内既有 `session_id or "default"` 口径）。"""
    store = MemoryStore()
    compactor = Compactor(memory=store)
    compactor.persist(compactor.compact([{"id": "h1", "content": "结论：部署完成"}]))

    entries = [e for e in store.audit() if e.source == "context"]
    assert {e.id for e in entries} == {"compaction.fact.default.0"}
    assert {e.session_id for e in entries} == {""}


def test_two_sessions_compaction_does_not_overwrite() -> None:
    """反例守门：两个会话各自压实 ⇒ 两条产物并存（改前 `compaction.fact.0` 后者覆盖前者）。"""
    store = MemoryStore()
    compactor = Compactor(memory=store)
    compactor.persist(
        compactor.compact([{"id": "h1", "content": "结论：会话甲完成"}]), session_id="A"
    )
    compactor.persist(
        compactor.compact([{"id": "h2", "content": "结论：会话乙完成"}]), session_id="B"
    )

    assert {e.id for e in store.audit() if e.source == "context"} == {
        "compaction.fact.A.0",
        "compaction.fact.B.0",
    }


# ---- 写入侧：宠物轨迹归属 ----


class _PetSpyLoop:
    """记录 `run` 收到的会话标识并返回受控结果的 fake loop。"""

    def __init__(self) -> None:
        self.session_ids: list[str] = []

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        self.session_ids.append(session_id)
        return LoopResult(reply="ok", trace_id="t1")


def test_pet_trajectory_carries_pet_session_id() -> None:
    """宠物唤醒经真实 loop 执行 ⇒ 携带**宠物会话标识**（不与主线未归属条目混同）。"""
    spy = _PetSpyLoop()
    session = PetSession(session_id="pet-1", loop=cast("LoopPlugin", spy))
    session.start(PetTask(kind=PetTaskKind.INFORMATION_GATHERING, goal="收集今日新闻"))
    session.wake()

    assert spy.session_ids == ["pet-1"]


def test_pet_default_session_id_is_non_blank() -> None:
    """缺省宠物会话标识为 uuid（始终非空）⇒ 宠物轨迹天然不进任何前台会话检索。"""
    session = PetSession()
    assert session.session_id
    assert not session.session_id.isspace()
    uuid.UUID(session.session_id)  # 形状即 uuid（可解析）


# ---- 写入侧：编排子任务归属 ----


class _SessionRecordingLoop(DefaultLoop):
    """记录 `astream` 收到的会话标识的测试循环（编排层即经流式入口执行子任务）。"""

    def __init__(self) -> None:
        super().__init__(planner=lambda ctx: Action(args={"reply": "ok"}))
        self.session_ids: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self.session_ids.append(session_id)
        async for event in super().astream(user_input, session_id=session_id):
            yield event


def _scheduler(loop: DefaultLoop) -> TaskScheduler:
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=loop)
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="a1", goal="t-one", acceptance="")]
    )
    return TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(agents=[profile]),
        state_machine=StateMachine(),
    )


def test_scheduler_forwards_session_id_to_sub_loop() -> None:
    """子任务执行携带**发起方会话标识** ⇒ 子轨迹按发起会话归属。"""
    loop = _SessionRecordingLoop()
    asyncio.run(_scheduler(loop).run("task", "goal", session_id="A"))

    assert loop.session_ids == ["A"]


def test_scheduler_default_keeps_sub_loop_call_unchanged() -> None:
    """未携带会话标识 ⇒ 子 loop 收到空串（与既往语义逐字一致）。"""
    loop = _SessionRecordingLoop()
    asyncio.run(_scheduler(loop).run("task", "goal"))

    assert loop.session_ids == [""]


# ---- notes：显式全局层（不参与会话隔离） ----


@pytest.mark.parametrize(
    "method", ["digest", "consult", "observe_turn", "pinned", "pinned_digest", "set_pinned"]
)
def test_notes_api_has_no_session_dimension(method: str) -> None:
    """可执行的全局层钉住：笔记层的 Consult / 写入面**不接受**会话维度。"""
    params = inspect.signature(getattr(NoteStore, method)).parameters
    assert not [name for name in params if "session" in name], method


def test_notes_consult_is_not_session_scoped(tmp_path: Path) -> None:
    """同一 query 在任意会话下的命中集相同 —— 笔记是被有意文档化的**刻意知识**。"""
    store = NoteStore(path=tmp_path)
    store.create("部署方案", title="部署方案", content="结论：用蓝绿发布")
    loop = DefaultLoop(notes_consult=store.digest)

    ctx_a = loop.perceive("部署方案", session_id="A")
    ctx_b = loop.perceive("部署方案", session_id="B")
    loop._consult_notes(ctx_a, "t")  # noqa: SLF001
    loop._consult_notes(ctx_b, "t")  # noqa: SLF001

    assert ctx_a.notes != ""
    assert ctx_a.notes == ctx_b.notes


def test_notes_pinned_is_not_session_scoped(tmp_path: Path) -> None:
    """常驻注入是全局文档层的另一条通道：注入面不接受会话维度（change 0149）。"""
    store = NoteStore(path=tmp_path)
    store.update(NoteEntry(note_id="约束", title="约束", content="必须 HTTPS", pinned=True))
    loop = DefaultLoop(pinned_notes_consult=store.pinned_digest)

    ctx_a = loop.perceive("任意", session_id="A")
    ctx_b = loop.perceive("任意", session_id="B")
    loop._load_pinned_notes(ctx_a, "t")  # noqa: SLF001
    loop._load_pinned_notes(ctx_b, "t")  # noqa: SLF001

    assert ctx_a.pinned_notes != ""
    assert ctx_a.pinned_notes == ctx_b.pinned_notes


def test_notes_promoted_note_is_global_layer(tmp_path: Path) -> None:
    """提升产出的 note 属全局文档层：不同会话上下文 Consult 命中集相同（change 0150 / ADR-0142）。

    `session_id` 仅是 `note_id` 的派生输入与来源标注，**不是**隔离维度。
    """
    store = NoteStore(path=tmp_path)
    summary = MemoryEntry(
        id="compaction.summary.A",
        layer="L2",
        content="结论：对外接口必须 HTTPS",
        tags=["compaction", "summary"],
        source="compaction",
        trace_id="compaction.A",
        session_id="A",
        kind="semantic",
    )
    note = promote_session_summary(store, summary, session_id="A")
    assert note is not None

    loop = DefaultLoop(notes_consult=store.digest)
    ctx_a = loop.perceive("对外接口", session_id="A")
    ctx_b = loop.perceive("对外接口", session_id="B")
    loop._consult_notes(ctx_a, "t")  # noqa: SLF001
    loop._consult_notes(ctx_b, "t")  # noqa: SLF001

    assert ctx_a.notes != ""
    assert ctx_a.notes == ctx_b.notes
