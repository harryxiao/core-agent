"""主循环会话轮级检查点（change 0214 / ADR-0204 / 台账 E151）。

规格 `durability`「会话轮级检查点」要求：主循环在轮首写 `done=False`、轮末写 `done=True`（同一
`turn.<trace_id>` 命名空间）；缺省关（`loop.turn_checkpoint`）⇒ 零写入；启动扫描对轮面**独立呈现**
且**不给** `task --resume`（续聊即恢复）。本文件证明五件事：

- 正常轮 ⇒ 同一 trace 的**两次写序**为 `False` → `True`（轮首 / 轮末，带会话与轮目标）；
- 中途中断 ⇒ 只留 `done=False`（不误报完结）；达上限的终止轮 ⇒ 仍写 `done=True`；
- 缺省关 ⇒ 零 `turn.` 检查点（零回归锚）；配置三面 + 非法值阻断启动；
- **分流**：`_recover_incomplete` 不把轮面当编排任务续跑；`_turn_incomplete` 只列未完结轮；
- **呈现**：轮面独立一段且**不含** `task --resume`；编排任务面照旧含（不混列）。

单元面全离线（无模型调用）；接线面用桩 provider 隔离出网。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.durability import CheckpointManager, CheckpointStore, CrashRecovery
from core.entry import _surface_incomplete, main
from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from core.loop import DefaultLoop, LoopEvent
from core.loop.protocol import Action, ActionResult
from core.runtime import _recover_incomplete, _turn_incomplete, build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)

_TURN_PREFIX = "turn."
_TURN_WRITES_PER_ROUND = 2  # 轮首（在途）+ 轮末（完结）各写一次


# ---- 桩 ----
class _StubProvider(LLMProvider):
    """替代 `StdlibLLMProvider` 的桩：构造签名兼容组合根调用点，调用期不出网。"""

    def __init__(self, **_kwargs: Any) -> None: ...

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="已完成：桩回复",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        yield LLMChunk(content="已完成：桩回复")

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


class _BoomLoop(DefaultLoop):
    """执行接缝恒抛：模拟「轮内被中断」。"""

    async def act(  # type: ignore[override]
        self, action: Action, trace_id: str, *, approved: bool = False
    ) -> ActionResult:
        raise RuntimeError("boom")


class _NoopCLIBridge:
    def __init__(self, *, api=None, connect_impl=None, session_id="") -> None:
        pass

    def connect(self) -> None:
        return None


async def _noop_stream(api, session_id: str, prompt: str) -> None:
    return None


async def _drain(events: AsyncIterator[LoopEvent]) -> list[LoopEvent]:
    return [event async for event in events]


def _recorder(calls: list[tuple[str, str, str, bool]]):
    def record(trace_id: str, session_id: str, goal: str, done: bool) -> None:
        calls.append((trace_id, session_id, goal, done))

    return record


# ---- 1. 单元：轮首 / 轮末写点 ----


def test_records_open_then_closed_on_normal_turn() -> None:
    """一轮 ⇒ 两次写：同一 trace、同会话同目标，`done` 由 `False` 转 `True`。"""
    calls: list[tuple[str, str, str, bool]] = []
    loop = DefaultLoop(turn_checkpoint=_recorder(calls))

    asyncio.run(_drain(loop.astream("目标：接线", session_id="s1")))

    assert [(c[1], c[2], c[3]) for c in calls] == [
        ("s1", "目标：接线", False),
        ("s1", "目标：接线", True),
    ], "轮首未完结 → 轮末已完结"
    assert calls[0][0] == calls[1][0], "两次写点同一 trace（⇒ 同一 task id）"


def test_round_limit_still_closes_turn() -> None:
    """达轮数上限的**终止轮**同样在轮末标记完结（写点在 `limit_reason` 分支之外）。"""
    calls: list[tuple[str, str, str, bool]] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="noop", args={}),  # 非终止动作 ⇒ 必然撞上限
        max_rounds=1,
        turn_checkpoint=_recorder(calls),
    )

    asyncio.run(_drain(loop.astream("目标：跑满", session_id="s1")))

    assert [c[3] for c in calls] == [False, True], "终止轮也走轮末写点"
    assert calls[-1][2] == "目标：跑满", "轮末仍带同一目标"


def test_interrupted_turn_leaves_open_only() -> None:
    """轮内抛错 ⇒ 只有轮首的 `done=False`（不误报完结、不谎报成功）。"""
    calls: list[tuple[str, str, str, bool]] = []
    loop = _BoomLoop(turn_checkpoint=_recorder(calls))

    with pytest.raises(RuntimeError):
        asyncio.run(_drain(loop.astream("目标：会炸", session_id="s1")))

    assert [c[3] for c in calls] == [False], "中断轮只留未完结标记"


def test_default_off_records_nothing() -> None:
    """缺省（未注入闭包）⇒ 零调用（零回归锚；`_turn_checkpoint` 为 `None`）。"""
    loop = DefaultLoop()

    assert loop._turn_checkpoint is None  # noqa: SLF001 — 注入面缺省断言
    asyncio.run(_drain(loop.astream("目标：无事", session_id="s1")))


# ---- 2. 分流：轮面不作编排任务续跑 ----


def _seed(checkpoints: CheckpointManager, task_id: str, session_id: str, **state: Any) -> None:
    checkpoints.create_checkpoint(task_id, session_id, {"done": False, **state})


def test_recover_incomplete_skips_turn_checkpoints(tmp_path: Path) -> None:
    """`_recover_incomplete` **不**为轮面产生续跑句柄（`turn.` 命名空间 / `kind="turn"`）。"""
    store = CheckpointStore(tmp_path / "cp.jsonl")
    checkpoints = CheckpointManager(store)
    _seed(checkpoints, "task-stale", "sess-1")
    _seed(checkpoints, f"{_TURN_PREFIX}t1", "sess-1", kind="turn", goal="g")

    handles = _recover_incomplete(checkpoints, CrashRecovery(store))

    assert [h.task_id for h in handles] == ["task-stale"], "轮面不入任务续跑面"


def test_turn_incomplete_lists_only_open_turns(tmp_path: Path) -> None:
    """`_turn_incomplete` 只列**未完结**轮：已完结（轮末 `done=True`）与编排任务都不出现。"""
    store = CheckpointStore(tmp_path / "cp.jsonl")
    checkpoints = CheckpointManager(store)
    _seed(checkpoints, f"{_TURN_PREFIX}open", "sess-a", kind="turn")
    checkpoints.create_checkpoint(f"{_TURN_PREFIX}closed", "sess-b", {"kind": "turn", "done": True})
    _seed(checkpoints, "task-stale", "sess-a")

    turns = _turn_incomplete(checkpoints)

    assert turns == [(f"{_TURN_PREFIX}open", "sess-a")], "只轮面、只在途"


# ---- 3. 呈现：轮面独立一段，不给续跑提示 ----


class _StubRuntime:
    """只承接呈现所需的两面（真实实现委派给 runtime 模块函数）。"""

    def __init__(self, checkpoints: CheckpointManager) -> None:
        self.checkpoints = checkpoints
        self.crash_recovery = CrashRecovery(checkpoints._store)  # noqa: SLF001 — 测试桩

    def recover(self) -> list[Any]:
        return _recover_incomplete(self.checkpoints, self.crash_recovery)

    def recover_turns(self) -> list[tuple[str, str]]:
        return _turn_incomplete(self.checkpoints)


def test_surface_renders_turn_without_resume_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """轮面独立呈现：报数量与会话，**不含** `task --resume`。"""
    checkpoints = CheckpointManager(CheckpointStore(tmp_path / "cp.jsonl"))
    _seed(checkpoints, f"{_TURN_PREFIX}t1", "sess-a", kind="turn", goal="g")

    with pytest.warns(UserWarning):
        _surface_incomplete(_StubRuntime(checkpoints))  # type: ignore[arg-type]

    err = capsys.readouterr().err
    assert "中断的会话轮" in err and "sess-a" in err
    assert "task --resume" not in err, "续聊即恢复 ⇒ 不给任务续跑提示"
    assert "未完成任务" not in err, "无编排任务 ⇒ 不报任务面"


def test_surface_keeps_task_and_turn_faces_separate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """任务面照旧提示续跑；轮面独立一段 —— 两者**不混列**。"""
    checkpoints = CheckpointManager(CheckpointStore(tmp_path / "cp.jsonl"))
    _seed(checkpoints, "task-stale", "sess-1")
    _seed(checkpoints, f"{_TURN_PREFIX}t1", "sess-2", kind="turn", goal="g")

    with pytest.warns(UserWarning):
        _surface_incomplete(_StubRuntime(checkpoints))  # type: ignore[arg-type]

    err = capsys.readouterr().err
    assert "task --resume task-stale" in err, "任务面续跑提示不变"
    assert f"task --resume {_TURN_PREFIX}t1" not in err, "轮面不得被当作任务提示"
    assert "中断的会话轮" in err and "sess-2" in err


def test_surface_silent_when_no_checkpoints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """无任何检查点 ⇒ 静默（两面都不打印）。"""
    _surface_incomplete(_StubRuntime(CheckpointManager(CheckpointStore(tmp_path / "cp.jsonl"))))  # type: ignore[arg-type]

    assert capsys.readouterr().err == ""


# ---- 4. 配置面（ConfigSpec 单一真源） ----


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


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _StubProvider)
    return tmp_path / "state"


def test_spec_declares_turn_checkpoint_key() -> None:
    """配置单一真源声明了该键（键 / CLI / env 三面一致）。"""
    specs = {spec.key: spec for spec in config_specs()}

    spec = specs["loop.turn_checkpoint"]
    assert spec.map_to == "loop.turn_checkpoint"
    assert spec.env_var == "CORE_LOOP_TURN_CHECKPOINT"


def test_config_default_is_off(tmp_path: Path) -> None:
    assert _manager(tmp_path).turn_checkpoint() is False


def test_config_yaml_enables(tmp_path: Path) -> None:
    assert _manager(tmp_path, "loop:\n  turn_checkpoint: true\n").turn_checkpoint() is True


def test_config_env_enables(tmp_path: Path) -> None:
    manager = _manager(tmp_path, environ={"CORE_LOOP_TURN_CHECKPOINT": "true"})

    assert manager.turn_checkpoint() is True


@pytest.mark.parametrize("value", ["maybe", ""])
def test_illegal_turn_checkpoint_blocks_startup(tmp_path: Path, value: str) -> None:
    """非法取值阻断启动（`loop` 为结构化段；静默兜底会把配置错误变成诡异行为）。

    空值（yaml 隐式 ``null``）也在列：读不出「开/关」即非法 —— 与 `block_plan` 同口径
    （词表外的字符串与 ``null`` 一律阻断；``1``/``0`` 等 feature flag 词表内取值合法）。
    """
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, f"loop:\n  turn_checkpoint: {value}\n")


# ---- 5. 接线：组合根（真闭包 + 真 store） ----


def _checkpoint_ids(runtime: object) -> list[str]:
    return [cp.task_id for cp in runtime.checkpoints.list_checkpoints()]  # type: ignore[attr-defined]


def test_flag_off_writes_no_turn_checkpoint(tmp_path: Path, state_dir: Path) -> None:
    """缺省关 ⇒ 跑完一轮仍**零** `turn.` 检查点（零回归锚）。"""
    runtime = build_runtime(_manager(tmp_path))

    runtime.loop.run("目标：缺省", session_id="s1")

    assert [t for t in _checkpoint_ids(runtime) if t.startswith(_TURN_PREFIX)] == []


def test_flag_on_writes_turn_checkpoint(tmp_path: Path, state_dir: Path) -> None:
    """旗开 ⇒ 主 loop 走**真闭包**：一轮后落 `turn.<trace_id>` 且已完结（`kind="turn"`）。"""
    runtime = build_runtime(_manager(tmp_path, "loop:\n  turn_checkpoint: true\n"))

    runtime.loop.run("目标：接线", session_id="s1")

    turn_ids = {t for t in _checkpoint_ids(runtime) if t.startswith(_TURN_PREFIX)}
    assert len(turn_ids) == 1, "同一轮两次写点共用同一 task id"
    [turn_id] = turn_ids
    checkpoints = runtime.checkpoints
    written = checkpoints.list_checkpoints(task_id=turn_id)
    assert len(written) == _TURN_WRITES_PER_ROUND, "轮首 / 轮末各写一次"
    latest = sorted(written, key=lambda cp: cp.ts)[-1]
    snapshot = checkpoints.get_snapshot(latest.checkpoint_id)
    assert snapshot.state["kind"] == "turn"
    assert snapshot.state["done"] is True, "轮末闭轮（桩回复 ⇒ 正常收尾）"
    assert snapshot.state["goal"] == "目标：接线"
    assert latest.session_id == "s1", "会话归属随检查点落盘"


# ---- 6. 入口呈现（真 CLI 路径） ----


def test_repl_startup_surfaces_interrupted_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """REPL 启动扫描呈现中断的会话轮，且**不**提示 `task --resume`（真入口锚）。"""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    CheckpointManager(CheckpointStore(state_dir / "checkpoints.jsonl")).create_checkpoint(
        f"{_TURN_PREFIX}t1", "sess-a", {"kind": "turn", "goal": "轮目标正文", "done": False}
    )
    monkeypatch.setenv("CORE_STATE_DIR", str(state_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("core.entry.CLIBridge", _NoopCLIBridge)
    monkeypatch.setattr("core.entry._stream", _noop_stream)

    assert main(["--config", _write_config(tmp_path)]) == 0

    err = capsys.readouterr().err
    assert "中断的会话轮" in err and "sess-a" in err
    assert "task --resume" not in err, "轮面不给续跑提示"
    assert "轮目标正文" not in err, "只报会话标识，不回显轮目标正文"
