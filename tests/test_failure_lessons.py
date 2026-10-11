"""「既往失败教训」注入块（change 0217 / ADR-0207 / 台账 E154）。

四面：
  * **零效应读**：`MemoryStore.failure_lessons` —— 只收 `failure` 标签、按会话、`ts` 降序有界、
    层无关（已归档 L4 仍可读）、**不改 `reuse_count` / 不产生效应**（故**不**经 `read()`）；
  * **注入块**：`LoopContext.failure_lessons` 非空 ⇒ planner 出**独立块**「既往失败教训：」；
    空 ⇒ 提示词**逐字不变**（**逐字锚**）；
  * **闭包注入**：`DefaultLoop(failure_lessons_consult=…)` —— 入参为**会话标识**；抛错**降级留痕**；
  * **接线与门控**：键 `loop.failure_lessons` 三面齐备、缺省**关**、非法取值**阻断启动**；
    关 ⇒ `exclude_fact_tags` **逐字**为既有 `{"steps"}`（**逐字锚**），开 ⇒ 追加 `failure`。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.loop import DefaultLoop, LoopContext
from core.loop.planner import LLMPlanner
from core.memory import MemoryEntry, MemoryStore
from core.observability import Tracer
from core.plugin_registry import EffectTracker
from core.runtime import build_runtime

# 单会话失败条目的默认条数（用例构造的轮数）
_ROUNDS = 5


def _store_with_failures(loop: DefaultLoop, session_id: str = "s1", rounds: int = _ROUNDS) -> None:
    # trace_id 带会话前缀 ⇒ 两条会话的失败条目 id 不撞（`loop.failure.<trace>` 是主键）
    for i in range(rounds):
        loop.remember(
            f"{session_id}-{i}",
            [{"round": 1, "ok": False, "error": "boom"}],
            session_id=session_id,
            failed=True,
        )


def _reuse(store: MemoryStore) -> dict[str, int]:
    return {str(entry.id): entry.reuse_count for entry in store.audit()}


# ── 1. 零效应读面 ────────────────────────────────────────────────────────────


def test_reads_only_failure_tagged_entries() -> None:
    """只收 `tags` 含 `failure` 的条目 —— 同轮轨迹条目（`trajectory`）**不**入选。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store)
    _store_with_failures(loop, rounds=1)

    ids = [str(entry.id) for entry in store.failure_lessons("s1")]

    assert ids == ["loop.failure.s1-0"]
    assert "loop.s1-0" not in ids


def test_orders_by_ts_desc_and_bounds() -> None:
    """`ts` **降序**（最近者在前）且**至多 `limit` 条**。"""
    store = MemoryStore()
    loop = DefaultLoop(memory=store)
    _store_with_failures(loop)

    newest_two = store.failure_lessons("s1", limit=2)

    assert [str(entry.id) for entry in newest_two] == [
        f"loop.failure.s1-{_ROUNDS - 1}",
        f"loop.failure.s1-{_ROUNDS - 2}",
    ]
    assert [entry.ts for entry in newest_two] == sorted(
        (entry.ts for entry in newest_two), reverse=True
    )
    assert len(store.failure_lessons("s1")) == _ROUNDS, "缺省 limit=5 收全部（恰 5 条）"


def test_session_filter_isolates() -> None:
    """按会话取 —— 他会话失败条目**不**混入。"""
    s1_rounds, s2_rounds = 2, 3
    store = MemoryStore()
    loop = DefaultLoop(memory=store)
    _store_with_failures(loop, "s1", rounds=s1_rounds)
    _store_with_failures(loop, "s2", rounds=s2_rounds)

    assert len(store.failure_lessons("s1")) == s1_rounds
    assert len(store.failure_lessons("s2")) == s2_rounds


def test_empty_session_id_returns_all() -> None:
    """缺省空串 ⇒ **不**按会话过滤（口径同 `session_chain`）。"""
    s1_rounds, s2_rounds = 2, 3
    store = MemoryStore()
    loop = DefaultLoop(memory=store)
    _store_with_failures(loop, "s1", rounds=s1_rounds)
    _store_with_failures(loop, "s2", rounds=s2_rounds)

    assert len(store.failure_lessons()) == s1_rounds + s2_rounds


def test_archived_layer_still_readable() -> None:
    """**层无关**：失败条目已迁 L4（遗忘归档）⇒ **仍可读**（失败证据不因迁移失联）。"""
    store = MemoryStore()
    store.write(
        "L4",
        MemoryEntry(
            id="loop.failure.archived",
            layer="L4",
            content="任务：X\n失败：boom",
            tags=["loop", "failure"],
            source="loop",
            trace_id="archived",
            session_id="s1",
            kind="episodic",
        ),
    )

    assert [str(entry.id) for entry in store.failure_lessons("s1")] == ["loop.failure.archived"]


def test_read_is_zero_effect() -> None:
    """**零效应锚**：读取前后 `reuse_count` **不变**、效应追踪器**无新增记录**、条目集不变。"""
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)
    loop = DefaultLoop(memory=store)
    _store_with_failures(loop, rounds=3)

    before_reuse = _reuse(store)
    before_effects = {f"t{i}": len(tracker.audit(f"t{i}")) for i in range(3)}

    store.failure_lessons("s1", limit=2)

    assert _reuse(store) == before_reuse, "不得强化复用计数（故不经 read()）"
    assert {f"t{i}": len(tracker.audit(f"t{i}")) for i in range(3)} == before_effects, (
        "不得产生任何效应"
    )


# ── 2. 注入块（planner 逐字锚）────────────────────────────────────────────────


def _planner() -> LLMPlanner:
    # `None` 仅占位（`_system_prompt` 不触碰 LLM）、不装装配器 ⇒ 只观察块装配本身
    return LLMPlanner(cast("Any", None))


def _ctx(**kwargs: Any) -> LoopContext:
    return LoopContext(messages=[{"role": "user", "content": "任务"}], **kwargs)


def test_loop_context_defaults_empty() -> None:
    """新字段缺省空 ⇒ 未接线路径不产块。"""
    assert LoopContext().failure_lessons == ""


def test_planner_injects_block_when_nonempty() -> None:
    """非空 ⇒ 出独立块「既往失败教训：」，正文原样在场。"""
    prompt = _planner()._system_prompt(  # noqa: SLF001 — 块装配判据
        _ctx(failure_lessons="- 任务：X\n- 失败：boom")
    )

    assert "既往失败教训：" in prompt
    assert "- 失败：boom" in prompt


def test_planner_omits_block_when_empty_verbatim() -> None:
    """**逐字锚**：空字段 ⇒ 提示词与**未引入该字段**时逐字相同。"""
    planner = _planner()

    assert planner._system_prompt(_ctx()) == planner._system_prompt(  # noqa: SLF001
        _ctx(failure_lessons="")
    )
    assert "既往失败教训：" not in planner._system_prompt(_ctx())  # noqa: SLF001


def test_block_precedes_skills_and_follows_notes() -> None:
    """块顺序：紧随「相关笔记」、先于「可用技能」。"""
    router = lambda _task: [{"skill_id": "s1", "version": "1"}]  # noqa: E731 — 桩路由
    planner = LLMPlanner(cast("Any", None), skill_router=cast("Any", router))
    prompt = planner._system_prompt(  # noqa: SLF001
        _ctx(notes="笔记正文", failure_lessons="- 失败：boom")
    )

    assert "可用技能：" in prompt, "桩路由须产出技能块（顺序比对需要）"
    assert prompt.index("相关笔记：") < prompt.index("既往失败教训：")
    assert prompt.index("既往失败教训：") < prompt.index("可用技能：")


# ── 3. 闭包注入（会话标识入参 + 降级留痕）────────────────────────────────────


def test_load_failure_lessons_passes_session_id() -> None:
    """钩子**入参为本轮会话标识**（按会话取教训），产物写入 `ctx.failure_lessons`。"""
    seen: list[str] = []

    def consult(session_id: str) -> str:
        seen.append(session_id)
        return f"- 会话 {session_id} 的教训"

    loop = DefaultLoop(failure_lessons_consult=consult)
    ctx = _ctx(session_id="s7")

    loop._load_failure_lessons(ctx, "t1")  # noqa: SLF001 — 注入判据

    assert seen == ["s7"]
    assert ctx.failure_lessons == "- 会话 s7 的教训"


def test_load_failure_lessons_degrades_on_error() -> None:
    """钩子抛错 ⇒ 置空字段 + 留痕（`failure_lessons_consult_failed`），**不**抛出。"""

    def boom(_session_id: str) -> str:
        raise RuntimeError("consult_failed")

    tracker = Tracer()
    loop = DefaultLoop(failure_lessons_consult=boom, tracer=tracker)
    ctx = _ctx(session_id="s1", failure_lessons="陈旧内容")

    loop._load_failure_lessons(ctx, "t1")  # noqa: SLF001

    assert ctx.failure_lessons == "", "降级 ⇒ 置空，不注入陈旧内容"
    kinds = [event.kind for event in tracker.replay("t1")]
    assert "failure_lessons_consult_failed" in kinds


def test_not_injected_leaves_field_untouched() -> None:
    """缺省未注入钩子 ⇒ **不触碰**字段（缺省关 ⇒ 逐字不变）。"""
    loop = DefaultLoop()
    ctx = _ctx()

    loop._load_failure_lessons(ctx, "t1")  # noqa: SLF001

    assert ctx.failure_lessons == ""


# ── 4. 配置三面、缺省关、非法阻断、接线条件化 ───────────────────────────────


_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


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


def test_spec_declares_failure_lessons() -> None:
    """单一真源：三面齐备、缺省**关**。"""
    spec = {spec.key: spec for spec in config_specs()}["loop.failure_lessons"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--loop.failure-lessons",
        "CORE_LOOP_FAILURE_LESSONS",
        False,
        "loop.failure_lessons",
    )


def test_default_off_and_yaml_env_enable(tmp_path: Path) -> None:
    """缺省关 ⇒ 不注入；yaml / env 两面对称可达（字符串口径与 feature flag 同集）。"""
    assert _manager(tmp_path).failure_lessons() is False
    assert _manager(tmp_path, "loop:\n  failure_lessons: true\n").failure_lessons() is True
    assert _manager(tmp_path, environ={"CORE_LOOP_FAILURE_LESSONS": "on"}).failure_lessons() is True


def test_illegal_value_blocks_startup(tmp_path: Path) -> None:
    """`loop` 是**结构化段** ⇒ 非法取值**阻断启动**（不静默归一）。"""
    with pytest.raises(ConfigurationError, match="非法失败教训块开关"):
        _manager(tmp_path, "loop:\n  failure_lessons: maybe\n")


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _exclude_tags(runtime: object) -> frozenset[str]:
    loop = cast("Any", runtime).loop
    return cast("frozenset[str]", loop._planner._assembler._exclude_fact_tags)


def test_exclude_fact_tags_verbatim_when_off(tmp_path: Path, state_dir: Path) -> None:
    """**逐字锚**：关（缺省）⇒ `exclude_fact_tags` **恰为**既有 `{"steps"}`、钩子未接线。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _exclude_tags(runtime) == frozenset({"steps"})
    assert cast("Any", runtime.loop)._failure_lessons_consult is None


def test_exclude_and_consult_wired_when_on(tmp_path: Path, state_dir: Path) -> None:
    """开 ⇒ `exclude_fact_tags` 追加 `failure`（专块承载 ⇒ 退出事实面）且钩子接主 loop。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "loop:\n  failure_lessons: true\n"))
    )

    assert _exclude_tags(runtime) == frozenset({"steps", "failure"})
    assert cast("Any", runtime.loop)._failure_lessons_consult is not None


def test_enabled_consult_renders_bounded_block(tmp_path: Path, state_dir: Path) -> None:
    """端到端（组合根闭包）：失败条目经钩子渲染为块，按会话取、有界（缺省 5 条）。"""
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "loop:\n  failure_lessons: true\n"))
    )
    loop = cast("Any", runtime.loop)
    _store_with_failures(loop, "s1", rounds=7)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 闭包不得触发任何告警
        block = loop._failure_lessons_consult("s1")

    assert block.count("\n- ") + 1 == _ROUNDS, "缺省至多 5 条（7 条失败、取最近 5 条）"
    assert "失败：" in block
    assert block.count("loop.failure.") == 0, "块内不暴露条目 id（只呈现正文）"
