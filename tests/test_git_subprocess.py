"""git 真实后端（stdlib subprocess）用例（change 0090 / Phase 20 C2）。

全部在 `tmp_path` 的**临时仓库**内以真实 `subprocess` 直调 git 往返，绝不在当前仓库执行写操作；
提交身份经 `GIT_AUTHOR_*` / `GIT_COMMITTER_*` 环境变量提供（免 `git config`）。
覆盖：读写往返 / 分支与合并（含冲突走 `MergeResult`）/ stash / 错误归一（不回显 stderr）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.git import (
    GitError,
    GitErrorCode,
    SubprocessGitBackend,
    build_backend,
)


def _repo(tmp_path, monkeypatch) -> tuple[SubprocessGitBackend, Path]:
    """建一个临时仓库并返回（后端, 仓库根 Path）。"""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "tester@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "tester@example.com")
    backend = SubprocessGitBackend(cwd=tmp_path)
    root = tmp_path / "repo"
    backend.init(str(root))
    return backend, root


def test_init_commit_status_log_roundtrip(tmp_path, monkeypatch) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    commit_id = backend.commit("chore: init")

    assert len(commit_id) == 40  # noqa: PLR2004 — git commit id 为 40 位十六进制
    status = backend.status()
    assert status.changed == [] and status.untracked == []
    entries = backend.log(count=5)
    assert entries[0].message == "chore: init"
    assert entries[0].commit_id == commit_id
    assert entries[0].author == "Tester"


def test_status_reports_changed_and_untracked(tmp_path, monkeypatch) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    (root / "a.txt").write_text("v1\n", encoding="utf-8")
    backend.commit("add a")
    (root / "a.txt").write_text("v2\n", encoding="utf-8")
    (root / "b.txt").write_text("new\n", encoding="utf-8")

    status = backend.status()
    assert "a.txt" in status.changed
    assert "b.txt" in status.untracked


def test_diff_reflects_change(tmp_path, monkeypatch) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    (root / "a.txt").write_text("v1\n", encoding="utf-8")
    backend.commit("add a")
    (root / "a.txt").write_text("v2\n", encoding="utf-8")
    assert "+v2" in backend.diff()


def test_branch_checkout_roundtrip(tmp_path, monkeypatch) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    (root / "a.txt").write_text("v1\n", encoding="utf-8")
    backend.commit("add a")
    base = backend.status().branch

    backend.branch("feature")
    backend.checkout("feature")
    assert backend.status().branch == "feature"
    backend.checkout(base)
    assert backend.status().branch == base


def test_merge_non_conflicting_succeeds(tmp_path, monkeypatch) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    (root / "a.txt").write_text("v1\n", encoding="utf-8")
    backend.commit("base")
    base = backend.status().branch
    backend.branch("feature")
    backend.checkout("feature")
    (root / "b.txt").write_text("side\n", encoding="utf-8")
    backend.commit("side")
    backend.checkout(base)

    result = backend.merge("feature")
    assert result.merged is True and result.conflict_files == []


def test_merge_conflict_reports_files(tmp_path, monkeypatch) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    backend.commit("base")
    base = backend.status().branch
    backend.branch("feature")
    backend.checkout("feature")
    (root / "a.txt").write_text("feature\n", encoding="utf-8")
    backend.commit("feature change")
    backend.checkout(base)
    (root / "a.txt").write_text("main\n", encoding="utf-8")
    backend.commit("main change")

    result = backend.merge("feature")
    assert result.merged is False
    assert "a.txt" in result.conflict_files


def test_stash_roundtrip(tmp_path, monkeypatch) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    (root / "a.txt").write_text("v1\n", encoding="utf-8")
    backend.commit("add a")
    (root / "a.txt").write_text("v2\n", encoding="utf-8")

    backend.stash(message="wip")
    assert (root / "a.txt").read_text(encoding="utf-8") == "v1\n"
    backend.stash_pop()
    assert (root / "a.txt").read_text(encoding="utf-8") == "v2\n"


def test_build_backend_returns_subprocess_adapter() -> None:
    """缺省工厂给出 stdlib subprocess 适配器（零三方依赖）。"""
    assert isinstance(build_backend(), SubprocessGitBackend)


def test_command_failure_normalized_and_no_stderr_echo(tmp_path, monkeypatch) -> None:
    """非仓库目录下执行 ⇒ 归一为 `GIT_COMMAND_FAILED`，且信息不回显 stderr（不泄露路径/凭据）。"""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Tester")
    empty = tmp_path / "empty"
    empty.mkdir()
    backend = SubprocessGitBackend(cwd=empty)

    with pytest.raises(GitError) as exc_info:
        backend.status()
    assert exc_info.value.code is GitErrorCode.GIT_COMMAND_FAILED
    assert "fatal" not in str(exc_info.value).lower()
    assert str(tmp_path) not in str(exc_info.value)


# ---- change 0138（账本 E79）：远程操作断线重试 / 指数退避 ----

_TRANSIENT = "fatal: unable to access 'https://host/x.git/': Could not resolve host: host"


def _flaky(monkeypatch, backend, script: list[tuple[int, str]]) -> dict[str, int]:
    """把后端的 `_invoke` 换成按 `script` 吐结果的桩，返回调用计数。"""
    calls = {"n": 0}

    def fake_invoke(args, *, cwd=None):
        i = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        code, stderr = script[i]
        return subprocess.CompletedProcess(list(args), code, "", stderr)

    monkeypatch.setattr(backend, "_invoke", fake_invoke)
    return calls


def test_remote_transient_jitter_retries_with_exponential_backoff(monkeypatch) -> None:
    """瞬态抖动 ⇒ 按指数退避重试，抖动两次后成功（退避序列 0.5 → 1.0）。"""
    delays: list[float] = []
    backend = SubprocessGitBackend(sleep=delays.append, attempts=3, backoff=0.5)
    calls = _flaky(monkeypatch, backend, [(128, _TRANSIENT), (128, _TRANSIENT), (0, "")])

    backend.pull()

    assert calls["n"] == 3  # noqa: PLR2004 — attempts=3
    assert delays == [0.5, 1.0]


def test_remote_retry_gives_up_at_attempt_limit(monkeypatch) -> None:
    """恒瞬态失败 ⇒ 达 `attempts` 上限后抛归一错误，不无限重试。"""
    delays: list[float] = []
    backend = SubprocessGitBackend(sleep=delays.append, attempts=3, backoff=0.5)
    calls = _flaky(monkeypatch, backend, [(128, _TRANSIENT)])

    with pytest.raises(GitError) as exc_info:
        backend.push()

    assert exc_info.value.code is GitErrorCode.GIT_COMMAND_FAILED
    assert calls["n"] == 3  # noqa: PLR2004 — attempts=3（达上限即抛，不无限重试）
    assert delays == [0.5, 1.0]  # 3 次尝试 ⇒ 2 次退避（末次不再睡）


def test_remote_auth_failure_not_retried(monkeypatch) -> None:
    """认证失败不重试（凭据不会自愈；spec「认证失败」要求明确报错）。"""
    delays: list[float] = []
    backend = SubprocessGitBackend(sleep=delays.append, attempts=3)
    calls = _flaky(monkeypatch, backend, [(128, "fatal: Authentication failed for 'https://h/'")])

    with pytest.raises(GitError) as exc_info:
        backend.pull()

    assert exc_info.value.code is GitErrorCode.GIT_AUTH_FAILED
    assert calls["n"] == 1
    assert delays == []


def test_remote_deterministic_failure_not_retried(monkeypatch) -> None:
    """确定性失败（非瞬态特征）不重试：一次即抛。"""
    delays: list[float] = []
    backend = SubprocessGitBackend(sleep=delays.append, attempts=3)
    calls = _flaky(monkeypatch, backend, [(128, "fatal: not a git repository")])

    with pytest.raises(GitError) as exc_info:
        backend.pull()

    assert exc_info.value.code is GitErrorCode.GIT_COMMAND_FAILED
    assert calls["n"] == 1
    assert delays == []


def test_remote_timeout_not_retried(monkeypatch) -> None:
    """超时即中止（spec「远程超时」Scenario：返回超时错误、不无限挂起/不重试）。"""
    delays: list[float] = []
    backend = SubprocessGitBackend(sleep=delays.append, attempts=3)
    calls = {"n": 0}

    def boom(*args, **kwargs):
        calls["n"] += 1
        raise subprocess.TimeoutExpired(cmd="git", timeout=1.0)

    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(GitError) as exc_info:
        backend.pull()

    assert exc_info.value.code is GitErrorCode.GIT_REMOTE_TIMEOUT
    assert calls["n"] == 1
    assert delays == []
