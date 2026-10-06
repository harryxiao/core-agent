"""`evolve implement` 操作面：筹备（`--dry-run`）→ 人工复核 → 落地（change 0112）。

执行器**只由操作面显式驱动**（规格明写：不挂 loop 热/冷路径节拍、不注册为任何工具）——本文件走
**真 argv**（`main([...])`）而 runtime 打桩，执行器为**真件**（补丁生产者 / 门禁执行器为假件），
源码树在 `tmp_path`：不出网、不跑真门、不碰真仓。缺省关闭一条走真装配（见 `test_feature_gating`）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.entry import main
from core.evolution import GenerationCandidate, PendingQueue
from core.evolution.executor import EvolutionExecutor, PatchProposal
from core.plugin_registry.effect_tracker import EffectTracker

_TARGET = "loop.default"
_PATH = "src/core/loop/default.py"
_ORIGINAL = "def run() -> None:\n    return None\n"
_PATCHED = "def run() -> None:\n    return 1\n"
_GATES = ("lint", "typecheck", "test", "build")
_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


class _GateOutcome:
    def __init__(self, passed: bool, reason: str = "") -> None:
        self.passed = passed
        self.reason = reason


class _Author:
    def __call__(self, _candidate: GenerationCandidate) -> PatchProposal:
        return PatchProposal(path=_PATH, content=_PATCHED)


class _Runner:
    def __init__(self, *, failing: frozenset[str] = frozenset()) -> None:
        self.failing = failing

    def __call__(self, kind: str) -> _GateOutcome:
        return _GateOutcome(
            kind not in self.failing, reason="" if kind not in self.failing else "未过"
        )


class _Engine:
    def __init__(self, candidate: GenerationCandidate) -> None:
        self._candidate = candidate

    def find(self, candidate_id: str) -> GenerationCandidate | None:
        return self._candidate if candidate_id == self._candidate.candidate_id else None

    def pending(self) -> list[GenerationCandidate]:
        return []


class _Evolution:
    def __init__(self, candidate: GenerationCandidate) -> None:
        self.engine = _Engine(candidate)


class _Runtime:
    def __init__(self, candidate: GenerationCandidate, executor: EvolutionExecutor | None) -> None:
        self.evolution = _Evolution(candidate)
        self.evolution_executor = executor


class _Harness:
    def __init__(
        self, executor: EvolutionExecutor, candidate: GenerationCandidate, cfg: str
    ) -> None:
        self.executor = executor
        self.candidate = candidate
        self.cfg = cfg

    def argv(self, *extra: str) -> list[str]:
        return ["--config", self.cfg, "evolve", "implement", self.candidate.candidate_id, *extra]

    def tree(self) -> Path:
        return self.executor.root / _PATH


def _harness(
    tmp_path: Path, monkeypatch: Any, *, failing: frozenset[str] = frozenset()
) -> _Harness:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    tree = tmp_path / _PATH
    tree.parent.mkdir(parents=True)
    tree.write_text(_ORIGINAL, encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    candidate = GenerationCandidate(
        generation=1,
        target_plugin=_TARGET,
        delta={"issue": "实施缺失"},
        kind="plugin",
        status="confirmed",
        risk_level="high",
    )
    queue = PendingQueue(path=tmp_path / "state" / "evolution-pending.json")
    queue.record(candidate)
    executor = EvolutionExecutor(
        author=_Author(),
        run_gate=_Runner(failing=failing),
        gates=_GATES,
        effects=EffectTracker(),
        queue=queue,
        root=tmp_path,
    )
    monkeypatch.setattr("core.entry.build_runtime", lambda *a, **kw: _Runtime(candidate, executor))
    return _Harness(executor, candidate, str(cfg))


def test_dry_run_shows_diff_and_stages_artifact(
    tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--dry-run`：筹备 + 打印补丁差异待复核；工作树**逐字不动**，制品落台账（可跨进程复核）。"""
    h = _harness(tmp_path, monkeypatch)

    assert main(h.argv("--dry-run")) == 0

    out = capsys.readouterr().out
    assert "待复核" in out
    assert f"--- {_PATH}" in out, "复核材料须是**看得见的差异**，不是「已筹备」四个字"
    assert h.tree().read_text(encoding="utf-8") == _ORIGINAL, "复核前不落地"
    assert h.executor.staged(h.candidate.candidate_id) is not None


def test_commit_applies_the_reviewed_patch(
    tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """复核落地：应用**被复核的那一份**制品（不重新产出补丁），结局 `implemented`。"""
    h = _harness(tmp_path, monkeypatch)
    assert main(h.argv("--dry-run")) == 0
    capsys.readouterr()

    assert main(h.argv("--approver", "me")) == 0

    assert "已实施" in capsys.readouterr().out
    assert h.tree().read_text(encoding="utf-8") == _PATCHED
    assert h.executor.staged(h.candidate.candidate_id) is None, "落地后不再是待复核项"


def test_commit_without_staging_is_refused(
    tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """未筹备直接落地 ⇒ 非零退出 + stderr，工作树不动（复核对象必须存在）。"""
    h = _harness(tmp_path, monkeypatch)

    assert main(h.argv("--approver", "me")) == 1

    assert "实施失败" in capsys.readouterr().err
    assert h.tree().read_text(encoding="utf-8") == _ORIGINAL


def test_failing_gate_is_refused_and_worktree_untouched(
    tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """门禁不过 ⇒ 非零退出 + stderr；工作树还原、无制品（不谎报筹备成功）。"""
    h = _harness(tmp_path, monkeypatch, failing=frozenset({"test"}))

    assert main(h.argv("--dry-run")) == 1

    assert "实施失败" in capsys.readouterr().err
    assert h.tree().read_text(encoding="utf-8") == _ORIGINAL
    assert h.executor.staged(h.candidate.candidate_id) is None


def test_unknown_candidate_is_refused(
    tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """候选不存在 ⇒ 非零退出 + stderr（不凭空筹备）。"""
    h = _harness(tmp_path, monkeypatch)

    assert main(["--config", h.cfg, "evolve", "implement", "nope", "--dry-run"]) == 1

    assert "候选不存在" in capsys.readouterr().err


def test_disabled_executor_refuses_and_explains(
    tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """执行器未装配（缺省关）⇒ 对齐既有「功能不可用不是进程错误」口径：stderr 说明 + 退出 0。"""
    h = _harness(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "core.entry.build_runtime",
        lambda *a, **kw: _Runtime(h.candidate, None),
    )

    assert main(h.argv("--dry-run")) == 0

    captured = capsys.readouterr()
    assert "evolution_executor" in captured.err
    assert "已关闭" in captured.err
    assert captured.out == ""


def test_pending_lists_the_staged_artifact(
    tmp_path: Path, monkeypatch: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """`evolve pending` 呈现待复核制品与门禁报告（人不必去翻台账 JSON）。"""
    h = _harness(tmp_path, monkeypatch)
    assert main(h.argv("--dry-run")) == 0
    capsys.readouterr()

    assert main(["--config", h.cfg, "evolve", "pending"]) == 0

    out = capsys.readouterr().out
    assert "待复核" in out
    assert h.candidate.candidate_id in out
    assert _PATH in out
    assert f"{len(_GATES)}/{len(_GATES)}" in out
