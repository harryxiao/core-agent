"""Procedural 端到端门禁（change 0199 / ADR-0189 / 台账 E136）。

**零 `src/` 改动** —— 只补「**任务过程 → 技能资产**」这条链的端到端锚，把 0196~0198 的
**两端**接起来。此前三段**各自**有单元锚：`0196` 只断言完成回调跑在工作线程
（`test_orchestration.py` 的线程 ident 用例）、`0197` 只单测纯函数 `compose_task_steps`
（`test_task_sop.py`）、`0198` 只单测 `SopExtractor` 的门分支（`test_skills.py`）—— 但
**没有任何用例**断言「真 `TaskScheduler` 跑完一个成功任务后，**真组合根装配**的任务级提炼器
真的把 SOP 入进**真技能库**」。回归时「哪一环断了」无法从端到端视角发觉。

本文件用**真组合根**（`build_runtime`）+ **真 `TaskScheduler`** + **真 `MemoryStore`**
（步序条目走真实写入路径）—— 只桩模型与子 Agent 执行单元两个**外部面**，不桩被测链路的任何一环。

反证（门禁非空过的证明，手工临时回退核对 ⇒ 见 ADR-0189）：

| 锚 | 回退手法 | 期望 |
|---|---|---|
| 1 | `runtime._finalize` 去掉 `sop_task_extractor.observe(...)` | 转红（无技能） |
| 1 | 任务级实例去 `namespace="task"` | 转红（`task_types` 无 `task::` 前缀） |
| 2 | 任务级实例 `gate=None`（去 `sop_gate_with`） | 转红（技能被发布） |
| 4 | `compose_task_steps` 改用 `outcome.reply` 拼行 | 转红（prompt 含 `_REPLY`） |
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from itertools import count
from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.loop import LoopEvent, LoopResult
from core.memory import MemoryEntry
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    Subtask,
    SubtaskDecomposer,
    SubtaskOutcome,
    TaskScheduler,
)
from core.runtime import Runtime, build_runtime
from core.skills import Skill

# 提炼器产出的 SOP 正文（桩模型返回此串 ⇒ 断言入库 `instructions` 逐字等于它）
_SOP_TEXT = "1. 读取输入\n2. 生成报告"

# 子 Agent 的回复（**不得**进提炼 prompt —— 见锚 4：过程取自记忆步序条目，非 `outcome.reply`）
_REPLY = "子任务回复-不应进提炼prompt"

# 任务目标（任务级归组键的词源）
_GOAL = "run quarterly report"

# 子 Agent 按目标返回确定性 trace_id（桩外部面）
_TRACE_BY_GOAL = {"run alpha": "t1", "run beta": "t2"}

# 灌入记忆的「任务过程」步序（每子任务一条 `loop.steps.<trace_id>` 条目）
_STEP_LINES = {"t1": "读取输入\n生成报告", "t2": "校验结论"}

# task_id 全局递增（同一状态机实例内不可复用已终态的 id）
_TASK_SEQ = count(1)


def _write_config(tmp_path: Path, *, judgment: bool = False) -> str:
    """LLM 段（+ 可选 judgment 段 ⇒ 开启 JEV 背书接缝）。"""
    text = (
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
    )
    if judgment:
        text += (
            "judgment:\n"
            "  provider: jev\n"
            "  model: systemone\n"
            "  base_url: http://jev.local\n"
            "  api_key: ${JEV_API_KEY}\n"
        )
    cfg = tmp_path / "config.yaml"
    cfg.write_text(text, encoding="utf-8")
    return str(cfg)


class _Reply:
    """模型回复替身（`_llm_text` 只要求 ``.content``）。"""

    def __init__(self, content: str) -> None:
        self.content = content


class _StubLoop:
    """子 Agent 执行单元替身（**外部面**）：按目标返回确定性 trace_id 的终态，不触网。"""

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        # 交接 prompt 首行为子任务目标（change 0247 追加原始目标/上下文段）
        goal = user_input.split("\n\n", 1)[0]
        yield LoopEvent("loop_finished", LoopResult(reply=_REPLY, trace_id=_TRACE_BY_GOAL[goal]))


def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, judgment: bool = False) -> Runtime:
    """真组合根装配 + 桩模型（提炼接缝）⇒ 离线端到端。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("JEV_API_KEY", "jev-sk")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path, judgment=judgment)))
    monkeypatch.setattr(runtime.llm, "completion", lambda _request: _Reply(_SOP_TEXT))
    return runtime


def _seed_steps(runtime: Runtime) -> None:
    """灌入「任务过程」步序（走**真实**记忆写入路径 ⇒ 与提炼器的回读面同源）。"""
    for trace_id, content in _STEP_LINES.items():
        runtime.memory.write(
            "L2",
            MemoryEntry(
                id=f"loop.steps.{trace_id}",
                layer="L2",
                content=content,
                tags=["loop", "steps"],
                source="loop",
                trace_id=trace_id,
            ),
        )


def _wire_stubs(runtime: Runtime) -> TaskScheduler:
    """把真编排器的**外部面**换成桩（decomposer 的 planner + 子 Agent 路由）。

    保留真 `TaskScheduler` 与真组合根注入的 ``on_done``（= ``_finalize``）⇒ 被测链路
    「完成回调 → 任务级提炼器 → 技能库」**逐环真实**。
    """

    def planner(_goal: str) -> list[Subtask]:
        return [
            Subtask(id="1", goal="run alpha", acceptance=""),
            Subtask(id="2", goal="run beta", acceptance=""),
        ]

    scheduler = runtime.orchestrator
    scheduler._decomposer = SubtaskDecomposer(planner=planner)  # noqa: SLF001 — 桩外部面
    scheduler._router = MultiAgentRouter(  # noqa: SLF001 — 桩外部面
        [AgentProfile(agent_id="main", capabilities=["run"], loop=_StubLoop())]
    )
    return scheduler


def _run(runtime: Runtime, times: int) -> None:
    """跑 `times` 次成功任务（同目标 ⇒ 同归组键 ⇒ 样本累加）。

    每次用**新** task_id：同一编排器实例内 task_id 是状态机身份（复用已 `DONE` 的 id 会
    触发非法转移），而归组键取自**目标**（`plan.goal`）⇒ 与 task_id 无关。
    """
    scheduler = _wire_stubs(runtime)
    for _ in range(times):
        task_id = f"task-{next(_TASK_SEQ)}"
        outcomes: list[SubtaskOutcome] = asyncio.run(scheduler.run(task_id, _GOAL))
        assert [o.ok for o in outcomes] == [True, True], "两子任务均应通过（否则任务不达 DONE）"


def _sop_skills(runtime: Runtime) -> list[Skill]:
    """技能库里由 SOP 提炼产生的技能（过滤神兽神通 / 内置循环技能）。"""
    library = runtime.skill_router._library  # noqa: SLF001 — 接线断言
    return [s for s in library.all_skills() if s.skill_id.startswith("skills.sop.")]


# ---- 锚 1：任务过程 → 技能资产（端到端连通） ----


def test_task_done_registers_task_level_sop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3 次成功 `DONE` ⇒ 任务级 SOP 入库：`instructions` 为提炼文本、`task_types` 含任务键。"""
    runtime = _runtime(tmp_path, monkeypatch)
    _seed_steps(runtime)

    _run(runtime, times=2)
    assert _sop_skills(runtime) == [], "未达阈值（3）前**不得**入库"

    _run(runtime, times=1)
    assert len(_sop_skills(runtime)) == 1
    skill = _sop_skills(runtime)[0]
    assert skill.instructions == _SOP_TEXT, "入库正文应为提炼器产出"
    assert skill.status == "draft", "SOP 先 draft（路由不可见），显式 activate 后生效"
    assert len(skill.task_types) == 1
    assert skill.task_types[0].startswith("task::"), "任务级面无命名空间前缀 ⇒ 会与单轮面混组"


# ---- 锚 2：质量门在真链路上生效 ----


def test_rejecting_gate_blocks_registration_in_real_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """注入拒绝门 ⇒ 全程**无**技能入库，且**有**门未过的留痕（证明门真的跑了）。"""
    monkeypatch.setattr("core.runtime.sop_gate_with", lambda _router: lambda _t, _s: False)
    runtime = _runtime(tmp_path, monkeypatch, judgment=True)
    _seed_steps(runtime)

    with pytest.warns(UserWarning, match="质量门未过") as caught:
        _run(runtime, times=3)

    assert _sop_skills(runtime) == [], "门未过 ⇒ 不得入库"
    assert len(caught) == 1, "门未过恰留痕一次（清组 ⇒ 不重复触发提炼）"


# ---- 锚 3：门禁非空过（反证，代码化） ----


def test_absent_gate_publishes_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 JEV（无门）⇒ 与今日一致地发布；与锚 2 成对 ⇒ **门**是二者唯一差异。"""
    runtime = _runtime(tmp_path, monkeypatch)  # 无 judgment 段 ⇒ gate=None
    _seed_steps(runtime)

    _run(runtime, times=3)

    assert len(_sop_skills(runtime)) == 1, "无门 ⇒ 发布路径逐字不变"


def test_sop_prompt_carries_memory_steps_not_subtask_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """过程取自**记忆步序条目**（`loop.steps.<trace>`），**不**取自 `SubtaskOutcome.reply`。

    ADR-0187「读 L2 而非 reply」决策的代码化反证：若回读面被改成拼接 `outcome.reply`
    （reply 截断 2000 字、不足以承载步序），本条转红。
    """
    runtime = _runtime(tmp_path, monkeypatch)
    _seed_steps(runtime)
    prompts: list[str] = []
    monkeypatch.setattr(runtime.llm, "completion", lambda request: _capture(prompts, request))

    _run(runtime, times=3)

    assert prompts, "达阈值应至少触发一次提炼调用"
    fed = prompts[0]
    assert "读取输入" in fed and "校验结论" in fed, "记忆步序条目必须进提炼 prompt"
    assert _REPLY not in fed, "子任务回复**不得**进提炼 prompt（过程取自记忆，非 reply）"


def _capture(prompts: list[str], request: Any) -> _Reply:
    """捕获真实投喂提炼器的 prompt（断言其**材料来源**）。"""
    prompts.append(request.messages[0].content)
    return _Reply(_SOP_TEXT)
