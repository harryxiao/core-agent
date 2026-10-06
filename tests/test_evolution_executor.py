"""原生执行器 `EvolutionExecutor`：范围守卫 / 归因一致 / 两阶段筹备→复核→落地（change 0112）。

规格 evolution「架构级候选的原生实施（可选）」：筹备（补丁 → 范围守卫 → 应用 → 跑冻结门 →
**回退**）→ 人工复核 → 落地 `implemented`。本文件**全部注入假件**（补丁生产者 / 门禁执行器），
不出网、不跑真门、不碰真仓：`root` 指向 `tmp_path` 里的**假源码树**。

守卫的两条独立判据各有一组用例：①**路径形状**（白名单 `src/core/` 内的 `.py` 减信任集，
`_scope_violation`）；②**路径与归因一致**（由候选 `target_plugin` 经约定解析得出且文件存在）。
候选先经 `_executor` 登记进台账 —— 制品与候选**同一条记录**承载，无记录的候选无处安放制品。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.evolution import EvolutionError, EvolutionErrorCode, GenerationCandidate, PendingQueue
from core.evolution.executor import (  # noqa: PLC2701 — 守卫判据逐条钉住
    COMMIT_TRACE,
    PREPARE_TRACE,
    EvolutionExecutor,
    PatchProposal,
    _scope_violation,
)
from core.permission import ApprovalRequest, ApprovalWorkflow
from core.plugin_registry.effect_tracker import EffectTracker

_TARGET = "loop.default"
_TARGET_PATH = "src/core/loop/default.py"
_ORIGINAL = "def run() -> None:\n    return None\n"
_PATCHED = "def run() -> None:\n    return 1\n"
_GATES = ("lint", "typecheck", "test", "build")


class _GateOutcome:
    def __init__(self, passed: bool, reason: str = "") -> None:
        self.passed = passed
        self.reason = reason


class _Author:
    """假补丁生产者：固定返回一份 `PatchProposal`（记录被调次数）。"""

    def __init__(self, path: str = _TARGET_PATH, content: str = _PATCHED) -> None:
        self.path = path
        self.content = content
        self.calls: list[str] = []

    def __call__(self, candidate: GenerationCandidate) -> PatchProposal:
        self.calls.append(candidate.candidate_id)
        return PatchProposal(path=self.path, content=self.content)


class _GateRunner:
    """假门禁执行器：按 `failing` 集合决定哪些门不过（记录被跑的门名）。"""

    def __init__(self, *, failing: frozenset[str] = frozenset()) -> None:
        self.failing = failing
        self.runs: list[str] = []

    def __call__(self, kind: str) -> _GateOutcome:
        self.runs.append(kind)
        return _GateOutcome(
            kind not in self.failing, reason=f"{kind} 未通过" if kind in self.failing else ""
        )


def _candidate(*, status: str = "confirmed", target: str = _TARGET) -> GenerationCandidate:
    return GenerationCandidate(
        generation=1,
        target_plugin=target,
        delta={"issue": "进化闭环最后一跳缺失"},
        kind="plugin",
        status=status,
        risk_level="high",
    )


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """假源码树：`<root>/src/core/loop/default.py` 就位（`root` 即执行器的仓库根）。"""
    target = tmp_path / _TARGET_PATH
    target.parent.mkdir(parents=True)
    target.write_text(_ORIGINAL, encoding="utf-8")
    return tmp_path


def _ticket(op: str = "evolution.implement", target: str = _TARGET, *, approved: bool = True):
    workflow = ApprovalWorkflow()
    ticket = workflow.create(
        ApprovalRequest(
            op=op,
            target=target,
            impact_summary="实施架构级候选",
            rollback_plan="按 EffectTracker undo 还原",
            trace_id="evolution",
        )
    )
    if approved:
        workflow.approve(ticket, approver="me")
    else:
        workflow.reject(ticket, approver="me")
    return ticket


def _executor(  # noqa: PLR0913 — 测试构造辅助
    root: Path,
    candidate: GenerationCandidate,
    *,
    author: _Author | None = None,
    runner: _GateRunner | None = None,
    queue: PendingQueue | None = None,
    effects: EffectTracker | None = None,
) -> tuple[EvolutionExecutor, _Author, _GateRunner, PendingQueue, EffectTracker]:
    """构造执行器：候选先登记进台账（制品与候选同一条记录承载）。"""
    author = author or _Author()
    runner = runner or _GateRunner()
    queue = queue or PendingQueue()
    effects = effects or EffectTracker()
    queue.record(candidate)
    executor = EvolutionExecutor(
        author=author, run_gate=runner, gates=_GATES, effects=effects, queue=queue, root=root
    )
    return executor, author, runner, queue, effects


def _read(root: Path) -> str:
    return (root / _TARGET_PATH).read_text(encoding="utf-8")


# ---- ① 路径形状：白名单 src/core/ 内的 .py 减信任集 ----

_VIOLATIONS = [
    "tests/test_evolution.py",  # 测试面（R1：不得自证通过）
    "pyproject.toml",  # 类型/构建配置
    "ruff.toml",
    ".pre-commit-config.yaml",
    "doc/openspec/specs/evolution/spec.md",  # 规格（自己的判据书）
    ".github/workflows/ci.yml",
    "src/core/ci_cd/pipeline.py",  # 门禁单一真源
    "src/core/ci_cd/__init__.py",  # 包出口重绑 GATE_COMMANDS 亦在信任集内
    "src/core/permission/approval.py",  # 审批关
    "src/core/configuration/manager.py",  # 开关判据
    "src/core/evolution/engine.py",  # 执行器自己的调用方与台账
    "src/core/evolution/pending.py",
    "src/core/runtime.py",  # 组合根
    "src/core/entry.py",  # 操作面 / 审批签发
    "src/core/persistence.py",  # 台账 IO
    "/etc/passwd",  # 绝对路径
    "src/core/notes/../../../../tmp/x.py",  # .. 段
    "src/core/notes/store.json",  # 非 .py
    "openspec/specs/evolution/spec.md",  # 符号链接别名路径
]


@pytest.mark.parametrize("path", _VIOLATIONS)
def test_scope_guard_rejects(path: str) -> None:
    """验证装置与信任链一律拒绝：触碰即不应用（R1 的具体机制）。"""
    assert _scope_violation(path) is not None


def test_scope_guard_allows_plain_source_module() -> None:
    """对照组：普通源码模块放行（守卫不是「一律拒绝」的空转）。"""
    assert _scope_violation(_TARGET_PATH) is None
    assert _scope_violation("src/core/notes/store.py") is None


# ---- ② 路径与归因一致 ----


def test_prepare_rejects_path_not_matching_attribution(tree: Path) -> None:
    """补丁路径 ≠ 归因约定解析出的路径 ⇒ 拒绝且**不应用**（守卫只查形状是不够的）。"""
    candidate = _candidate()
    executor, _, runner, queue, _ = _executor(
        tree, candidate, author=_Author(path="src/core/notes/store.py")
    )

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED
    assert runner.runs == [], "守卫前置：门禁一次都不该跑"
    assert _read(tree) == _ORIGINAL
    assert queue.implementation_of(candidate.candidate_id) is None


def test_prepare_rejects_missing_target_file(tmp_path: Path) -> None:
    """归因目标文件不存在 ⇒ 拒绝（fail-closed，不凭约定凭空造文件）。"""
    candidate = _candidate(target="notes.store")
    executor, _, _, queue, _ = _executor(
        tmp_path, candidate, author=_Author(path="src/core/notes/store.py")
    )

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED
    assert queue.implementation_of(candidate.candidate_id) is None


def test_prepare_rejects_trusted_module_even_when_attribution_matches(tree: Path) -> None:
    """归因**一致**也不够：目标落在信任集（进化引擎自身）内 ⇒ 守卫拒绝（R1 的真机制）。"""
    trusted = tree / "src/core/evolution/worker.py"
    trusted.parent.mkdir(parents=True)
    trusted.write_text("X = 1\n", encoding="utf-8")
    candidate = _candidate(target="evolution.worker")
    executor, _, runner, _, _ = _executor(
        tree, candidate, author=_Author(path="src/core/evolution/worker.py")
    )

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED
    assert runner.runs == []
    assert trusted.read_text(encoding="utf-8") == "X = 1\n"


def test_prepare_rejects_non_internal_target(tree: Path) -> None:
    """归因白名单外的目标（工具 id）即便文件存在也不得实施（架构级 = 内部核心模块）。"""
    stray = tree / "src/core/tools/web_fetch.py"
    stray.parent.mkdir(parents=True)
    stray.write_text("X = 1\n", encoding="utf-8")
    candidate = _candidate(target="tools.web_fetch")
    executor, _, runner, _, _ = _executor(
        tree, candidate, author=_Author(path="src/core/tools/web_fetch.py")
    )

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED
    assert runner.runs == []


# ---- 筹备：应用 → 跑冻结门 → 回退，制品落台账 ----


def test_prepare_restores_worktree_and_stages_artifact(tree: Path) -> None:
    """筹备跑完全部门禁后**回退**工作树，制品（补丁 + 原内容 + 门禁报告）落台账。"""
    candidate = _candidate()
    executor, author, runner, queue, effects = _executor(tree, candidate)

    record = executor.prepare(candidate)

    assert author.calls == [candidate.candidate_id]
    assert runner.runs == list(_GATES), "四道门禁全跑（冻结门，不自选）"
    assert _read(tree) == _ORIGINAL, "筹备不得留下工作树改动"
    assert record.before == _ORIGINAL
    assert record.content == _PATCHED
    assert record.gated is True and record.committed is False
    assert {name: entry["passed"] for name, entry in record.gate.items()} == dict.fromkeys(
        _GATES, True
    )
    assert queue.implementation_of(candidate.candidate_id) is not None, "制品落既有候选台账"
    report = effects.rollback(f"{PREPARE_TRACE}.{candidate.candidate_id}")
    assert report.reverted and not report.undo_failed, "筹备的临时应用是可逆效应"


def test_prepare_requires_confirmed_candidate(tree: Path) -> None:
    """未人工确认的候选不得筹备（人工关前置，fail-closed）。"""
    candidate = _candidate(status="pending")
    executor, _, runner, _, _ = _executor(tree, candidate)

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED
    assert runner.runs == []


def test_prepare_gate_failure_rolls_back_without_artifact(tree: Path) -> None:
    """任一门禁不过 ⇒ 回退工作树、**不落制品**、抛结构化门禁失败（不谎报筹备成功）。"""
    candidate = _candidate()
    executor, _, _, queue, _ = _executor(
        tree, candidate, runner=_GateRunner(failing=frozenset({"test"}))
    )

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.GATE_REJECTED
    assert _read(tree) == _ORIGINAL
    assert queue.implementation_of(candidate.candidate_id) is None


def test_prepare_rejects_a_candidate_outside_the_ledger(tree: Path) -> None:
    """候选不在台账 ⇒ 拒绝（制品与候选同一条记录承载，无记录即无处安放，不静默造条目）。"""
    candidate = _candidate()
    executor = EvolutionExecutor(
        author=_Author(),
        run_gate=_GateRunner(),
        gates=_GATES,
        effects=EffectTracker(),
        queue=PendingQueue(),
        root=tree,
    )

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED
    assert _read(tree) == _ORIGINAL


def test_prepare_detects_leftover_dirty_worktree(tree: Path) -> None:
    """上次筹备未回退（工作树与记录的原内容不符）⇒ 拒绝，不把脏内容当成「原内容」。"""
    candidate = _candidate()
    executor, _, _, queue, _ = _executor(tree, candidate)
    executor.prepare(candidate)
    (tree / _TARGET_PATH).write_text("def run() -> None:\n    return 99\n", encoding="utf-8")

    with pytest.raises(EvolutionError) as exc:
        executor.prepare(candidate)

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_STALE
    assert queue.implementation_of(candidate.candidate_id) is not None


# ---- 复核 → 落地 ----


def test_commit_without_artifact_is_rejected(tree: Path) -> None:
    """未筹备直接落地 ⇒ 拒绝（复核对象必须存在）。"""
    candidate = _candidate()
    executor, _, _, _, _ = _executor(tree, candidate)

    with pytest.raises(EvolutionError) as exc:
        executor.commit(candidate, approval=_ticket())

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED
    assert _read(tree) == _ORIGINAL


@pytest.mark.parametrize(
    "ticket_factory",
    [
        pytest.param(lambda: None, id="无审批单"),
        pytest.param(lambda: _ticket(approved=False), id="审批被拒"),
        pytest.param(lambda: _ticket(target="other.plugin"), id="目标不符"),
        pytest.param(lambda: _ticket(op="evolution.publish"), id="操作标识不可区分"),
    ],
)
def test_commit_requires_matching_implement_ticket(tree: Path, ticket_factory: Any) -> None:
    """复核关 fail-closed：缺失 / 未批准 / 目标不符 / 复用了 `confirm` 那张单 ⇒ 不落地。"""
    candidate = _candidate()
    executor, _, _, _, _ = _executor(tree, candidate)
    executor.prepare(candidate)

    with pytest.raises(EvolutionError) as exc:
        executor.commit(candidate, approval=ticket_factory())

    assert exc.value.code == EvolutionErrorCode.CONFIRM_REQUIRED
    assert _read(tree) == _ORIGINAL, "复核未过 ⇒ 工作区逐字不变"
    assert candidate.status == "confirmed"


def test_commit_rejects_drifted_worktree(tree: Path) -> None:
    """筹备之后目标文件被外部改动 ⇒ `IMPLEMENT_STALE`，不把补丁覆盖到漂移内容上。"""
    candidate = _candidate()
    executor, _, _, _, _ = _executor(tree, candidate)
    executor.prepare(candidate)
    (tree / _TARGET_PATH).write_text("def run() -> None:\n    return 7\n", encoding="utf-8")

    with pytest.raises(EvolutionError) as exc:
        executor.commit(candidate, approval=_ticket())

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_STALE
    assert _read(tree).endswith("return 7\n")


def test_commit_applies_patch_and_reports_implemented(tree: Path) -> None:
    """复核通过 ⇒ 永久落地 + 结局 `implemented`（不是 `accepted`、不是 `published`）。"""
    candidate = _candidate()
    executor, _, _, queue, effects = _executor(tree, candidate)
    executor.prepare(candidate)

    outcome = executor.commit(candidate, approval=_ticket())

    assert outcome.status == "implemented"
    assert outcome.candidate is candidate
    assert _read(tree) == _PATCHED
    assert candidate.status == "implemented"
    record = queue.implementation_of(candidate.candidate_id)
    assert record is not None and record.committed is True
    report = effects.rollback(f"{COMMIT_TRACE}.{candidate.candidate_id}")
    assert report.reverted and not report.undo_failed, "落地记录可逆效应（P2）"
    assert _read(tree) == _ORIGINAL


def test_commit_is_not_repeatable(tree: Path) -> None:
    """已落地的候选再落地 ⇒ 拒绝（不重复记账、不重复记录效应）。"""
    candidate = _candidate()
    executor, _, _, _, _ = _executor(tree, candidate)
    executor.prepare(candidate)
    executor.commit(candidate, approval=_ticket())

    with pytest.raises(EvolutionError) as exc:
        executor.commit(candidate, approval=_ticket())

    assert exc.value.code == EvolutionErrorCode.IMPLEMENT_REJECTED


def test_staged_is_empty_until_prepare(tree: Path) -> None:
    """`staged` 是「可复核制品」查询：未筹备 / 已落地都为空。"""
    candidate = _candidate()
    executor, _, _, _, _ = _executor(tree, candidate)

    assert executor.staged(candidate.candidate_id) is None
    executor.prepare(candidate)
    assert executor.staged(candidate.candidate_id) is not None
    executor.commit(candidate, approval=_ticket())
    assert executor.staged(candidate.candidate_id) is None
