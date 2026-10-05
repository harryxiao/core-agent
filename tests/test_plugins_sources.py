"""插件外部来源解析用例（change 0093 / Phase 20 C6）。

覆盖规格 plugin-registry「插件来源与安装」的四类来源**发现**：
git-repo（**真实**临时仓库克隆 + 根目录 `core-plugin.json` + 临时工作区不残留）、
market-registry（注入 fetcher / 缺省 urllib 边经 `file://` 离线往返）、
mcp-endpoint（解析期零网络），
以及 `InstallDispatcher.resolve` 四源分派与 CLI `plugin install --source` 端到端。

git-repo 的来源地址用 `tmp_path` 下的**本地仓库**（git 支持本地克隆 ⇒ 全程离线，无需网络/凭据）。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

from core.entry import _state_path, main
from core.git import GitError, GitErrorCode
from core.plugin_registry import DomainError, ErrorCode, PluginSource
from core.plugins import (
    MANIFEST_FILENAME,
    Cloner,
    Fetcher,
    InstallDispatcher,
    resolve_git_repo,
    resolve_market_registry,
    resolve_mcp_endpoint,
)
from core.skills import SkillLibrary
from core.tools import ToolProvider

_MANIFEST = {"skill_id": "skills.demo.git", "description": "from git", "param_schema": {}}
_ENDPOINT = "https://plugin.example.com:9000/mcp"


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """提交身份经环境变量提供（免 `git config`），对齐 test_git_subprocess.py。"""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "tester@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "tester@example.com")


def _make_repo(tmp_path: Path, manifest: dict[str, Any] | None) -> Path:
    """建一个临时 git 仓库；`manifest` 为 None 时不写 `core-plugin.json`。"""
    root = tmp_path / "plugin-repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    if manifest is not None:
        (root / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init", "--allow-empty"], cwd=root, check=True)
    return root


def _dispatcher(
    *, cloner: Cloner | None = None, fetcher: Fetcher | None = None
) -> InstallDispatcher:
    return InstallDispatcher(
        skill_library=SkillLibrary(),
        tool_provider=ToolProvider(),
        cloner=cloner,
        fetcher=fetcher,
    )


# ---- git-repo ----


def test_git_repo_source_reads_manifest_from_clone(tmp_path: Path) -> None:
    """真实 stdlib 克隆（不注入 cloner）：本地仓库 → 读根目录 manifest。"""
    root = _make_repo(tmp_path, _MANIFEST)
    assert resolve_git_repo(str(root)) == _MANIFEST


def test_git_repo_source_without_manifest_is_unreachable(tmp_path: Path) -> None:
    root = _make_repo(tmp_path, None)
    with pytest.raises(DomainError) as exc_info:
        resolve_git_repo(str(root))
    assert exc_info.value.code is ErrorCode.SOURCE_NOT_FOUND
    assert MANIFEST_FILENAME in exc_info.value.message


def test_git_repo_source_clone_failure_normalized(tmp_path: Path) -> None:
    """来源不存在 ⇒ 归一 `SOURCE_NOT_FOUND`（真实 git 克隆失败，不注入）。"""
    with pytest.raises(DomainError) as exc_info:
        resolve_git_repo(str(tmp_path / "no-such-repo"))
    assert exc_info.value.code is ErrorCode.SOURCE_NOT_FOUND


def test_git_repo_source_cloner_failure_normalized_and_no_credential_echo(tmp_path: Path) -> None:
    """注入 cloner 抛 `GitError` ⇒ 归一 `SOURCE_NOT_FOUND`，且地址中的 userinfo 不回显。"""

    def _boom(_url: str, _dest: Path) -> None:
        raise GitError(GitErrorCode.GIT_AUTH_FAILED, "git 远程认证失败")

    location = "https://deploy:token-abc123@example.com/private/plugin.git"
    with pytest.raises(DomainError) as exc_info:
        resolve_git_repo(location, cloner=_boom)
    assert exc_info.value.code is ErrorCode.SOURCE_NOT_FOUND
    assert "token-abc123" not in exc_info.value.message
    assert "deploy" not in exc_info.value.message


def test_git_repo_source_leaves_no_worktree_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """临时工作区在解析后清理（不残留）：系统临时目录下不新增任何条目。"""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    root = _make_repo(tmp_path, _MANIFEST)

    resolve_git_repo(str(root))
    assert list(scratch.iterdir()) == []


# ---- market-registry ----


def test_market_registry_uses_injected_fetcher() -> None:
    calls: list[str] = []

    def _fetch(url: str) -> dict[str, Any]:
        calls.append(url)
        return _MANIFEST

    url = "https://market.example.com/plugins/demo.json"
    assert resolve_market_registry(url, fetcher=_fetch) == _MANIFEST
    assert calls == [url]


def test_market_registry_default_fetcher_fetches_document_offline(tmp_path: Path) -> None:
    """缺省 fetcher 是真实 stdlib HTTP 客户端：`file://` 文档离线往返证明该路径可用。"""
    document = tmp_path / "plugin.json"
    document.write_text(json.dumps(_MANIFEST), encoding="utf-8")
    assert resolve_market_registry(document.as_uri()) == _MANIFEST


def test_market_registry_failure_normalized_and_no_credential_echo() -> None:
    def _boom(_url: str) -> dict[str, Any]:
        raise RuntimeError("connection reset")  # noqa: TRY003 — 模拟注入边的任意故障

    location = "https://market.example.com/plugins/demo.json?token=secret-xyz"
    with pytest.raises(DomainError) as exc_info:
        resolve_market_registry(location, fetcher=_boom)
    assert exc_info.value.code is ErrorCode.SOURCE_NOT_FOUND
    assert "secret-xyz" not in exc_info.value.message


def test_market_registry_domain_error_passes_through() -> None:
    """fetcher 自己抛出领域错误 ⇒ 原样透传（不二次包装）。"""
    raised = DomainError(ErrorCode.SOURCE_NOT_FOUND, "市场不可达")

    def _boom(_url: str) -> dict[str, Any]:
        raise raised

    with pytest.raises(DomainError) as exc_info:
        resolve_market_registry("https://market.example.com/p.json", fetcher=_boom)
    assert exc_info.value is raised


def test_market_registry_default_fetcher_rejects_invalid_document(tmp_path: Path) -> None:
    document = tmp_path / "broken.json"
    document.write_text("{not json", encoding="utf-8")
    with pytest.raises(DomainError) as exc_info:
        resolve_market_registry(document.as_uri())
    assert exc_info.value.code is ErrorCode.SOURCE_NOT_FOUND


# ---- mcp-endpoint ----


def test_mcp_endpoint_synthesizes_manifest_without_network() -> None:
    assert resolve_mcp_endpoint(_ENDPOINT) == {
        "name": "plugin.example.com",
        "url": _ENDPOINT,
    }


# ---- 分派 ----


def test_dispatcher_routes_all_four_sources(tmp_path: Path) -> None:
    local = tmp_path / "local.json"
    local.write_text(json.dumps(_MANIFEST), encoding="utf-8")
    root = _make_repo(tmp_path, _MANIFEST)
    dispatcher = _dispatcher(fetcher=lambda _url: _MANIFEST)

    assert dispatcher.resolve(PluginSource.LOCAL_PATH, str(local)) == _MANIFEST
    assert dispatcher.resolve(PluginSource.GIT_REPO, str(root)) == _MANIFEST
    assert dispatcher.resolve(PluginSource.MARKET_REGISTRY, "https://m.example.com/p") == _MANIFEST
    assert dispatcher.resolve(PluginSource.MCP_ENDPOINT, _ENDPOINT)["url"] == _ENDPOINT


def test_dispatcher_local_path_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DomainError) as exc_info:
        _dispatcher().resolve(PluginSource.LOCAL_PATH, str(tmp_path / "nope.json"))
    assert exc_info.value.code is ErrorCode.SOURCE_NOT_FOUND


# ---- CLI ----


def test_plugin_install_git_repo_source_persists_skill(tmp_path: Path) -> None:
    """`plugin install --source git-repo`：真实本地仓库 ⇒ 技能落持久库（跨进程可见）。"""
    root = _make_repo(tmp_path, _MANIFEST)
    assert main(["plugin", "install", str(root), "--kind", "skill", "--source", "git-repo"]) == 0
    reopened = SkillLibrary(path=_state_path("skills.json"))
    assert reopened.lookup("skills.demo.git").description == "from git"


def test_plugin_install_default_source_is_still_local_path(tmp_path: Path) -> None:
    manifest = tmp_path / "p.json"
    manifest.write_text(json.dumps(_MANIFEST), encoding="utf-8")
    assert main(["plugin", "install", str(manifest), "--kind", "skill"]) == 0
    assert SkillLibrary(path=_state_path("skills.json")).lookup("skills.demo.git") is not None


def test_plugin_install_rejects_unknown_source() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["plugin", "install", "somewhere", "--source", "ftp"])
    assert exc_info.value.code == 2  # noqa: PLR2004 — argparse 用法错误固定退出码 2
