"""M4 长任务 token 次线性基准（change 0274 / ADR-0264 / 台账 E210）。

离线确定性 harness：固定任务序列 × N 轮，在**同一会话**内驱动真实 `DefaultLoop`
（`LLMPlanner` + 桩 provider + 本地有界摘要器），逐轮记录 `LLMPlanner.last_prompt_tokens()`
曲线 ⇒ 输出斜率并与「全量原文回灌」线性基线对比。零网络、零真实模型、零时钟依赖
（注入步进时钟）。

规格：`loop`「长任务 token 增长基准」。**不设绝对阈值门禁**（PA-10 选项 C 未采纳）；
本文件断言的是**机制性相对判据**（外置曲线远期饱和、且低于线性基线），绝对阈值另行裁决。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from core.context import Compactor
from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from core.loop import DefaultLoop
from core.loop.planner import LLMPlanner
from core.memory import MemoryEntry, MemoryStore, TranscriptStore

# 固定任务序列规模与载荷尺寸（字符 ⇒ token 走共享估计器 ``len // 4``，逐轮等长可复现）。
_TASK_COUNT = 24
_TASK_CHARS = 240
_REPLY_CHARS = 480
_SUMMARY_CHARS = 600
_SESSION = "bench-m4"


class _StubLLM(LLMProvider):
    """离线桩 provider：按当前任务编号产等长回复，不触网、不真调模型。"""

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        content = _reply_for(request)
        return LLMResponse(
            content=content,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        yield LLMChunk(content=_reply_for(request))

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


class _SteppingClock:
    """确定性时钟：每调用一次前进 1 秒（维护节拍按轮触发，不依赖墙钟）。"""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        self._now += 1.0
        return self._now


def _fixed(text: str, width: int) -> str:
    """重复填充并截断到**精确**字符宽度（每轮载荷等长 ⇒ 曲线可复现）。"""
    return (text * (width // len(text) + 1))[:width]


def _task_text(index: int) -> str:
    return _fixed(f"任务{index:02d}：" + "执行样例步骤。", _TASK_CHARS)


def _reply_for(request: LLMRequest) -> str:
    current = request.messages[-1].content
    index = current[2:4] if current.startswith("任务") else "00"
    return _fixed(f"完成{index}：" + "结论与记录。", _REPLY_CHARS)


def _bounded_summarizer(material: list[MemoryEntry]) -> str:
    """有界滚动摘要器（模型有界输出的确定性替身）：保留合并内容尾部定长字符。"""
    merged = "；".join(entry.content for entry in material)
    return merged[-_SUMMARY_CHARS:]


async def _run(count: int, *, externalize: bool) -> tuple[list[int], MemoryStore]:
    """在单一会话内驱动 ``count`` 轮，返回逐轮 ``prompt_tokens`` 曲线与会话记忆。

    ``externalize=True``：维护节拍每轮触发 ⇒ 产会话摘要 + 中层摘要，三层滑窗生效。
    ``externalize=False``：关闭摘要器与维护节拍，``history_turns=count`` ⇒ 全量原文回灌
    （线性基线）。
    """
    memory = MemoryStore(summarizer=_bounded_summarizer if externalize else None)
    planner = LLMPlanner(_StubLLM(), model="stub")
    loop = DefaultLoop(
        planner=planner,
        memory=memory,
        transcript=TranscriptStore(),  # path=None ⇒ 纯内存
        compactor=Compactor(memory=memory, step_threshold=100),
        token_budget=65536,  # 远高于单轮占用 ⇒ 预算闸门不介入（只测装配增长）
        history_turns=20 if externalize else count,
        maintenance_interval=1.0 if externalize else 0.0,
        clock=_SteppingClock(),
    )
    curve: list[int] = []
    for index in range(count):
        async for _ in loop.astream(_task_text(index), session_id=_SESSION):
            pass
        curve.append(planner.last_prompt_tokens())
    return curve, memory


def _slope(points: list[int]) -> float:
    """最小二乘斜率（每任务点）。"""
    n = len(points)
    if n <= 1:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = sum(points) / n
    denom = sum((x - mean_x) ** 2 for x in range(n))
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(range(n), points, strict=True)) / denom


def test_m4_prompt_tokens_grow_sublinearly() -> None:
    """外置生效 ⇒ 远期曲线饱和，且整体增长低于全量回灌基线（次线性判定）。"""
    curve, memory = asyncio.run(_run(_TASK_COUNT, externalize=True))
    linear, _ = asyncio.run(_run(_TASK_COUNT, externalize=False))

    late = _slope(curve[-8:])
    print(f"externalized curve: {curve}")  # noqa: T201 — 基准输出供人工查看
    print(f"linear baseline:    {linear}")  # noqa: T201
    print(f"slope externalized={_slope(curve):.2f} baseline={_slope(linear):.2f} late={late:.2f}")  # noqa: T201
    assert len(curve) == _TASK_COUNT
    assert all(tokens > 0 for tokens in curve)

    assert memory.summary_for(_SESSION) is not None, "首轮维护节拍应产出会话摘要"
    # 远期饱和：短带（10 轮）与两层摘要均到界 ⇒ 每轮装配占用恒定。
    assert max(curve[-8:]) - min(curve[-8:]) == 0, "远期曲线应完全饱和（无逐轮漂移）"
    # 次线性：外置曲线整体斜率显著低于全量回灌，且末轮占用更小。
    assert _slope(curve) < _slope(linear)
    assert curve[-1] < linear[-1]


def test_m4_benchmark_is_deterministic() -> None:
    """同一 harness 重放两次 ⇒ 逐轮曲线逐值一致（无时钟/随机/网络依赖）。"""
    first, _ = asyncio.run(_run(_TASK_COUNT, externalize=True))
    second, _ = asyncio.run(_run(_TASK_COUNT, externalize=True))
    assert first == second
