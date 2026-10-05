"""git 真实后端（stdlib subprocess）用例（change 0090 / Phase 20 C2）。

全部在 `tmp_path` 的**临时仓库**内以真实 `subprocess` 直调 git 往返，绝不在当前仓库执行写操作；
提交身份经 `GIT_AUTHOR_*` / `GIT_COMMITTER_*` 环境变量提供（免 `git config`）。
覆盖：读写往返 / 分支与合并（含冲突走 `MergeResult`）/ stash / 错误归一（不回显 stderr）。
"""

from __future__ import annotations

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
