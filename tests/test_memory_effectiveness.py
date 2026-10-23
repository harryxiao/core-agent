"""记忆效果离线评测：有 / 无记忆回放（change 0311 / P2-5，规格「记忆效果离线评测」）。

两臂走**同一**真实链路（`DefaultLoop` + `LLMPlanner` + `DynamicAssembler`），仅记忆库不同：

- **有记忆**：每个任务独立库，灌入 gold 事实 + 干扰事实；
- **无记忆**：空库。

桩 provider 只在提示词出现 `GOLD[...]` 标记时答对 —— 标记只存在于 gold 事实中 ⇒ 成功率提升
只可能来自事实被检索并注入提示词。纯离线、零网络、零时钟依赖（冻结时间戳）。

墙钟仅报告、不作门禁（机器噪声）；成功判据只依赖确定性输出。
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from core.context import DynamicAssembler
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
from core.memory import MemoryEntry, MemoryStore

# 冻结时间戳：recency 衰减恒 1.0（无时钟噪声）。
_FREEZE_TS = 4_000_000_000.0
# 门禁：有记忆成功率下限（规格「记忆效果离线评测」）。
_MIN_WITH_MEMORY = 0.9

# (问题, gold 答案, gold 事实, 干扰事实)。答案以 `GOLD[答案]` 标记包裹，仅存于 gold 事实。
_TASKS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "阿尔法项目的部署端口是多少",
        "7311",
        "阿尔法项目的部署端口是 7311。标记 GOLD[7311]",
        ("阿尔法项目的代码仓库位于团队空间。", "阿尔法项目的文档每周五评审。"),
    ),
    (
        "贝塔服务的默认并发上限是多少",
        "32",
        "贝塔服务的默认并发上限是 32。标记 GOLD[32]",
        ("贝塔服务的灰度发布按周进行。", "贝塔服务的监控面板在运维台。"),
    ),
    (
        "伽马数据库的每日备份时刻是几点",
        "03:00",
        "伽马数据库的每日备份时刻是 03:00。标记 GOLD[03:00]",
        ("伽马数据库的实例规格已升级。", "伽马数据库的慢查询日志保留一周。"),
    ),
    (
        "德尔塔模块的负责人是谁",
        "林可",
        "德尔塔模块的负责人是林可。标记 GOLD[林可]",
        ("德尔塔模块的接口文档已归档。", "德尔塔模块的重构排在下季度。"),
    ),
    (
        "艾普西隆告警通道的默认接收人是谁",
        "值班组",
        "艾普西隆告警通道的默认接收人是值班组。标记 GOLD[值班组]",
        ("艾普西隆告警通道在夜间静默。", "艾普西隆告警的分级规则沿用旧版。"),
    ),
    (
        "泽塔流水线的构建产物保留天数",
        "14",
        "泽塔流水线的构建产物保留天数是 14 天。标记 GOLD[14]",
        ("泽塔流水线的清理任务在周末执行。", "泽塔流水线支持手动重跑。"),
    ),
)


class _MarkerStub(LLMProvider):
    """桩 provider：提示词含 `GOLD[...]` 才答对；否则答「未知」。"""

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        text = "\n".join(message.content for message in request.messages)
        answer = _marker_answer(text)
        content = json.dumps({"reply": f"答案：{answer}" if answer else "未知"}, ensure_ascii=False)
        return LLMResponse(
            content=content,
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        response = await self.acompletion(request)
        yield LLMChunk(content=response.content)

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


def _marker_answer(text: str) -> str:
    start = text.find("GOLD[")
    if start < 0:
        return ""
    end = text.find("]", start)
    return text[start + len("GOLD[") : end] if end > 0 else ""


def _entry(entry_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="bench",
        trace_id=f"bench.{entry_id}",
        ts=_FREEZE_TS,
        session_id="",
        kind="semantic",
    )


def _store(index: int, *, with_memory: bool) -> MemoryStore:
    store = MemoryStore()
    if not with_memory:
        return store
    _, _, gold, distractors = _TASKS[index]
    store.write("L2", _entry(f"gold-{index}", gold))
    for offset, content in enumerate(distractors):
        store.write("L2", _entry(f"distractor-{index}-{offset}", content))
    return store


def _run_task(index: int, *, with_memory: bool) -> tuple[bool, int]:
    """单任务单臂回放：返回（是否答对, 末轮 prompt token）。"""
    query, gold, _, _ = _TASKS[index]
    store = _store(index, with_memory=with_memory)
    planner = LLMPlanner(_MarkerStub(), model="stub", assembler=DynamicAssembler(memory=store))
    loop = DefaultLoop(planner=planner, memory=store)

    result = loop.run(query)

    return gold in result.reply, planner.last_prompt_tokens()


def _replay(*, with_memory: bool) -> dict[str, Any]:
    started = time.perf_counter()
    outcomes = [_run_task(index, with_memory=with_memory) for index in range(len(_TASKS))]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    successes = sum(1 for ok, _ in outcomes if ok)
    return {
        "success_rate": successes / len(outcomes),
        "success_flags": tuple(ok for ok, _ in outcomes),
        "prompt_tokens": sum(tokens for _, tokens in outcomes),
        "elapsed_ms": elapsed_ms,
    }


def test_memory_improves_replay_success_rate() -> None:
    """有记忆成功率 ≥ 0.9 且严格高于无记忆；事实确实进入提示词（token 更大）。"""
    with_memory = _replay(with_memory=True)
    without = _replay(with_memory=False)
    print(  # noqa: T201 — 基准输出供人工查看
        f"with_memory={with_memory['success_rate']:.2f} "
        f"without={without['success_rate']:.2f} "
        f"tokens={with_memory['prompt_tokens']}/{without['prompt_tokens']} "
        f"ms={with_memory['elapsed_ms']:.1f}/{without['elapsed_ms']:.1f}"
    )

    assert with_memory["success_rate"] >= _MIN_WITH_MEMORY
    assert with_memory["success_rate"] > without["success_rate"]
    assert without["success_rate"] < _MIN_WITH_MEMORY
    assert with_memory["prompt_tokens"] > without["prompt_tokens"]


def test_replay_is_deterministic() -> None:
    """同一任务集两次独立回放 ⇒ 成功判定与 prompt token 完全一致。"""
    first = _replay(with_memory=True)
    second = _replay(with_memory=True)

    assert first["success_flags"] == second["success_flags"]
    assert first["prompt_tokens"] == second["prompt_tokens"]

    first_off = _replay(with_memory=False)
    second_off = _replay(with_memory=False)
    assert first_off["success_flags"] == second_off["success_flags"]
    assert first_off["prompt_tokens"] == second_off["prompt_tokens"]
