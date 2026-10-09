"""轮级失败的独立沉淀面（change `0179` / ADR-0170 / 台账 E116）。

失败既不是 SOP（`SopExtractor.observe` 对 `ok=False` 直接丢弃，自陈「教训沉淀走 memory 通道」），
也不该只作为轨迹散文里的一行——本测守护新契约：**轮级失败**（终止动作失败 / 预算或轮次终止 /
不可解析输出）在既有两条之外**另立第三条** L2 条目 `loop.failure.<trace_id>`
（标签 `loop` + `failure`），内容＝任务 + 原因 + 失败轮次 + 失败动作，逐行脱敏、整体有界；
**成功轮不写**（逐字回归）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.llm_provider import LLMResponse, TokenUsage
from core.loop import Action, DefaultLoop, LLMPlanner, LoopContext
from core.loop.default import (
    _FAILURE_REASON_FALLBACK,
    _MAX_MEMORY_ENTRY,
    _MAX_STEP_LINE,
    failure_digest,
)
from core.memory import REDACTED, MemoryStore
from core.plugin_registry import EffectTracker
from core.tools import Tool, ToolDef, ToolProvider

_SECRET = "sk-" + "a" * 20


def _echo_tool() -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="tools.echo",
            description="echo",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=[],
            reversible=True,
        ),
        handler=lambda text: f"echo:{text}",
    )


class _FakeLLM:
    """恒定内容的假 LLM：让「不可解析输出」走**真实** `LLMPlanner._parse` 路径。"""

    def __init__(self, content: str) -> None:
        self._content = content

    def completion(self, request: Any) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="fake",
            model="test-model",
        )

    async def acompletion(self, request: Any) -> LLMResponse:
        return self.completion(request)


def _parse(content: str) -> Action:
    """复刻 `tests/test_loop_output_protocol.py` 的取法：经 planner 拿到真实解析动作。"""
    provider = ToolProvider()
    provider.register(_echo_tool())
    planner = LLMPlanner(_FakeLLM(content), tools=provider)
    return asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "hi"}])))


def _contents(store: MemoryStore) -> dict[str, str]:
    return {str(entry.id): entry.content for entry in store.audit()}


# ---- Layer A：纯函数 `failure_digest` ----


def test_failure_digest_renders_task_reason_rounds_and_steps() -> None:
    digest = failure_digest(
        [
            {"round": 1, "ok": True},
            {"round": 2, "ok": False, "error": "boom"},
            {"reply": "算了"},  # 无 `ok` 键 ⇒ 不是失败轮，不入摘要
        ],
        ["tools.echo（text: x） → 错误：bad", "tools.echo（text: y） → ok"],
        reason="LOOP_LIMIT_EXCEEDED",
        task="查一下天气",
    )
    assert digest.splitlines() == [
        "任务：查一下天气",
        "失败：LOOP_LIMIT_EXCEEDED",
        "round 2 failed boom",
        "tools.echo（text: x） → 错误：bad",
    ]


def test_failure_digest_falls_back_when_reason_missing() -> None:
    """`reason` 缺省（如不可解析输出轮）⇒ 恒定兜底文案；无失败轮时仍非空。"""
    assert failure_digest([], [], reason="", task="") == f"失败：{_FAILURE_REASON_FALLBACK}"


def test_failure_digest_redacts_each_line() -> None:
    digest = failure_digest(
        [{"round": 1, "ok": False, "error": f"提交失败 {_SECRET}"}],
        [f"tools.echo（text: {_SECRET}） → 错误：拒绝 {_SECRET}"],
        reason=f"认证失败 {_SECRET}",
        task=f"用 {_SECRET} 登录",
    )
    assert _SECRET not in digest
    lines = digest.splitlines()
    assert len(lines) == 4  # noqa: PLR2004 — 任务 / 失败 / 失败轮 / 失败步，四行各一
    assert all(REDACTED in line for line in lines), "逐行脱敏（每行都含密钥的那一行被替换）"


def test_failure_digest_is_bounded() -> None:
    steps = [f"tools.echo（text: {'x' * 300}） → 错误：{'y' * 300}" for _ in range(100)]
    digest = failure_digest([], steps, reason="r", task="t")
    assert 0 < len(digest) <= _MAX_MEMORY_ENTRY


def test_failure_digest_bounds_long_task() -> None:
    digest = failure_digest([], [], reason="r", task="t" * 5000)
    assert len(digest.splitlines()[0]) <= _MAX_STEP_LINE


# ---- Layer B：写入接线 ----


def test_failed_turn_writes_dedicated_failure_entry() -> None:
    store = MemoryStore()

    DefaultLoop(memory=store).remember(
        "t1",
        [{"round": 1, "ok": False, "error": "boom"}, {"reply": "没成"}],
        session_id="s1",
        steps=["tools.echo（text: x） → 错误：bad"],
        failed=True,
        reason="LOOP_LIMIT_EXCEEDED",
        task="查天气",
    )

    entries = {str(entry.id): entry for entry in store.audit()}
    assert set(entries) == {"loop.t1", "loop.steps.t1", "loop.failure.t1"}  # 三条**并存**
    failure = entries["loop.failure.t1"]
    assert failure.layer == "L2"
    assert failure.kind == "episodic"
    assert failure.tags == ["loop", "failure"]
    assert failure.trace_id == "t1"
    assert failure.session_id == "s1"
    assert failure.source == "loop"
    assert "任务：查天气" in failure.content
    assert "失败：LOOP_LIMIT_EXCEEDED" in failure.content
    assert "round 1 failed boom" in failure.content


def test_success_turn_writes_no_failure_entry() -> None:
    """成功轮**逐字回归**：既不写失败条目，既有两条内容也不变。"""
    store = MemoryStore()

    DefaultLoop(memory=store).remember(
        "t2",
        [{"round": 1, "ok": True}, {"reply": "成了"}],
        steps=["tools.echo（text: x） → echo:x"],
    )

    assert _contents(store) == {
        "loop.t2": "round 1 ok\n成了",
        "loop.steps.t2": "tools.echo（text: x） → echo:x",
    }


def test_failure_entry_without_steps_still_written() -> None:
    """纯回复轮失败（无工具调用）⇒ 无行动序列条目，但**仍有**失败条目。"""
    store = MemoryStore()

    DefaultLoop(memory=store).remember(
        "t3", [{"round": 1, "ok": False, "error": "parse"}], failed=True
    )

    assert set(_contents(store)) == {"loop.t3", "loop.failure.t3"}


def test_failure_entry_is_reversible() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)

    DefaultLoop(memory=store).remember("t4", [{"round": 1, "ok": False}], failed=True)
    assert "loop.failure.t4" in _contents(store)

    tracker.rollback("t4")

    assert "loop.failure.t4" not in _contents(store)


def test_no_memory_wired_is_a_noop() -> None:
    DefaultLoop().remember("t5", [{"round": 1, "ok": False}], failed=True)  # 不抛


def test_failure_entry_is_retrievable() -> None:
    store = MemoryStore()
    DefaultLoop(memory=store).remember(
        "t6",
        [{"round": 1, "ok": False, "error": "权限不足"}],
        session_id="s2",
        failed=True,
        task="删除生产库",
    )

    hits = {str(entry.id) for entry in store.read("删除生产库 权限不足", session_id="s2")}

    assert "loop.failure.t6" in hits


# ---- Layer B：端到端终止语义 ----


def test_round_limit_termination_writes_failure_entry() -> None:
    """轮次终止（`LOOP_LIMIT_EXCEEDED`）⇒ 失败条目带该原因。"""
    store = MemoryStore()

    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        memory=store,
        max_rounds=1,
    )
    result = loop.run("一直转")

    assert "LOOP_LIMIT_EXCEEDED" in result.reply
    failure = next(entry for entry in store.audit() if str(entry.id).startswith("loop.failure."))
    assert failure.tags == ["loop", "failure"]
    assert "失败：LOOP_LIMIT_EXCEEDED" in failure.content


def test_token_budget_termination_writes_failure_entry() -> None:
    store = MemoryStore()

    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        memory=store,
        token_budget=1,
    )
    loop.run("hi")

    failure = next(entry for entry in store.audit() if str(entry.id).startswith("loop.failure."))
    assert "失败：TOKEN_BUDGET_EXCEEDED" in failure.content


def test_tool_failure_inside_turn_does_not_write_failure_entry() -> None:
    """轮内工具失败但本轮**成功**收尾（ReAct 自愈）⇒ **不写**失败条目（按用户裁决的轮级口径）。"""

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"missing": "x"})  # schema 不符 ⇒ 该步失败
        return Action(args={"reply": "自愈完成"})

    store = MemoryStore()
    result = DefaultLoop(planner=planner, memory=store, max_rounds=5).run("hi")

    assert result.reply == "自愈完成"
    assert not [entry for entry in store.audit() if str(entry.id).startswith("loop.failure.")]


def test_unparseable_output_writes_failure_entry_without_raw_output() -> None:
    """不可解析输出轮（`turn_failed` 的另一来源）⇒ 写失败条目，但 `raw_output` **不入**记忆。

    `raw_output` 的禁入面是 ADR-0161 明文的（SHALL NOT 进入转录 / 记忆 / 笔记）——
    失败条目**不得**成为它的旁路。
    """
    raw = '{"tool_id": "tools.echo",'
    # 先经真实 planner 取得「不可解析 ⇒ 终止且失败」的动作；再交给循环（避免嵌套事件循环）
    fail_action = _parse(raw)

    store = MemoryStore()
    loop = DefaultLoop(planner=lambda ctx: fail_action, memory=store)
    result = loop.run("hi")

    assert result.failed is True
    failure = next(entry for entry in store.audit() if str(entry.id).startswith("loop.failure."))
    assert raw not in failure.content
    assert f"失败：{_FAILURE_REASON_FALLBACK}" in failure.content
