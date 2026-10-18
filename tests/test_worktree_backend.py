"""git 工作树 / 分支原语用例（change 0284 / ADR-0274）。

全部在 `tmp_path` 的临时仓库内以真实 `subprocess` 直调 git 往返，绝不在当前仓库执行写操作。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.git import GitError, GitErrorCode, SubprocessGitBackend, build_backend


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[SubprocessGitBackend, Path]:
    """建一个有一次提交的临时仓库并返回（后端, 仓库根 Path）。"""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "tester@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "tester@example.com")
    backend = SubprocessGitBackend(cwd=tmp_path)
    root = tmp_path / "repo"
    backend.init(str(root))
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    backend.commit("chore: init")
    return backend, root


def test_repo_root_resolves_from_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _backend, root = _repo(tmp_path, monkeypatch)
    (root / "sub").mkdir()

    assert SubprocessGitBackend(cwd=root / "sub").repo_root() == str(root.resolve())


def test_worktree_add_list_remove_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    wt = tmp_path / "wt"
    branch = "core-agent/wt-test"
    backend.worktree_add(str(wt), branch=branch)

    assert (wt / "a.txt").read_text(encoding="utf-8") == "hello\n"
    entries = backend.worktree_list()
    paths = {entry.path for entry in entries}
    assert str(wt.resolve()) in paths
    assert branch in {entry.branch for entry in entries}
    assert backend.branch_exists(branch) is True

    backend.worktree_remove(str(wt))
    backend.delete_branch(branch, force=True)

    assert not wt.exists()
    assert backend.branch_exists(branch) is False
    assert str(wt.resolve()) not in {entry.path for entry in backend.worktree_list()}
    assert root.exists()


def test_worktree_add_without_commit_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "tester@example.com")
    backend = SubprocessGitBackend(cwd=tmp_path)
    root = tmp_path / "empty"
    backend.init(str(root))

    with pytest.raises(GitError) as caught:
        backend.worktree_add(str(tmp_path / "wt"), branch="core-agent/wt-empty")

    assert caught.value.code is GitErrorCode.GIT_COMMAND_FAILED
    assert "stderr" not in caught.value.message
    assert not (tmp_path / "wt").exists()


def test_worktree_remove_dirty_requires_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, _root = _repo(tmp_path, monkeypatch)
    wt = tmp_path / "wt"
    backend.worktree_add(str(wt), branch="core-agent/wt-dirty")
    (wt / "dirty.txt").write_text("unsaved\n", encoding="utf-8")

    with pytest.raises(GitError) as caught:
        backend.worktree_remove(str(wt))
    assert caught.value.code is GitErrorCode.GIT_WORKTREE_DIRTY

    backend.worktree_remove(str(wt), force=True)
    assert not wt.exists()


def test_worktree_list_parses_detached_and_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, root = _repo(tmp_path, monkeypatch)
    detached = tmp_path / "detached"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(detached), "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    entries = backend.worktree_list()
    by_path = {entry.path: entry for entry in entries}
    assert root.resolve() == Path(by_path[str(root.resolve())].path)
    assert by_path[str(detached.resolve())].branch is None
    assert by_path[str(detached.resolve())].head


def test_worktree_rejects_option_like_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backend, _root = _repo(tmp_path, monkeypatch)

    with pytest.raises(GitError) as caught:
        backend.worktree_add("-x", branch="core-agent/wt-evil")
    assert caught.value.code is GitErrorCode.GIT_COMMAND_FAILED
    assert not backend.branch_exists("core-agent/wt-evil")


def test_build_backend_accepts_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _backend, root = _repo(tmp_path, monkeypatch)

    assert build_backend(root).repo_root() == str(root.resolve())
