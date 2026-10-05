"""外部插件来源解析器（plugins）。

``InstallDispatcher.resolve`` 的真实外部来源实现：git-repo（克隆后读 manifest）、
market-registry（拉取 manifest 文档）、mcp-endpoint（由端点串合成 manifest）。三类来源的
外部边（git / HTTP）均可注入，**缺省实现走 stdlib**（``core.git`` 的 subprocess 后端与
``urllib.request``），契合 ADR-0044「核心零三方依赖」红线。

凭据口径：市场鉴权经**注入的 fetcher** 携带，不写进 URL；任何回显一律经 :func:`_safe`
剥掉 userinfo 与 query（对齐 ADR-0085「不回显可能含凭据的地址」）。

对应规格：doc/openspec/specs/plugin-registry/spec.md「插件来源与安装」
接口：doc/03-interfaces/plugin-registry-interface.md §8
"""

from __future__ import annotations

import json
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

from core.git import build_backend
from core.mcp import default_endpoint_name
from core.plugin_registry import DomainError, ErrorCode

# git-repo 来源约定：仓库**根目录**下的 manifest 文件名（对外契约，见接口文档 §8）
MANIFEST_FILENAME = "core-plugin.json"

# HTTP manifest 文档体上限（防超大响应打爆内存）与连接超时
_MAX_MANIFEST_BYTES = 1 << 20
_HTTP_TIMEOUT = 15.0

_USER_AGENT = "core-agent/plugin-installer"

_T = TypeVar("_T")

Cloner = Callable[[str, Path], None]
"""克隆边：``(url, dest)`` 把仓库克隆到 ``dest``（失败抛任意异常）。"""

Fetcher = Callable[[str], dict[str, Any]]
"""拉取边：``url -> manifest``（鉴权由实现自行携带，不走 URL）。"""


def _safe(url: str) -> str:
    """回显用安全地址：**剥掉 userinfo 与 query**（可能含凭据 / token，对齐 git 后端口径）。

    不用 ``urlsplit(...).port``（畸形端口会 raise），改 ``netloc.rpartition("@")`` 取主机段。
    """
    parts = urlsplit(url)
    if not parts.scheme:
        return url
    netloc = parts.netloc.rpartition("@")[2]
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _parse_manifest(raw: bytes, location: str) -> dict[str, Any]:
    """字节 → manifest dict；解码 / JSON 非法一律归一 ``SOURCE_NOT_FOUND``。"""
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise DomainError(ErrorCode.SOURCE_NOT_FOUND, f"manifest 非法: {_safe(location)}") from exc


def _clone_with_git(url: str, dest: Path) -> None:
    """缺省克隆边：stdlib subprocess 直调 git CLI（复用 change 0090 的 git 后端）。"""
    build_backend().clone(url, str(dest))


def _http_json(url: str) -> dict[str, Any]:
    """缺省拉取边：stdlib ``urllib`` GET manifest 文档（有界读取；异常归一来源不可达）。"""
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
            raw = response.read(_MAX_MANIFEST_BYTES)
    except Exception as exc:  # noqa: BLE001 — 网络 / HTTP / 解析异常统一映射来源不可达
        raise DomainError(ErrorCode.SOURCE_NOT_FOUND, f"来源不可达: {_safe(url)}") from exc
    return _parse_manifest(raw, url)


def _normalize(operation: str, location: str, action: Callable[[], _T]) -> _T:
    """执行外部边：任意故障归一 ``SOURCE_NOT_FOUND``，领域错误原样透传（不二次包装）。"""
    try:
        return action()
    except DomainError:
        raise
    except Exception as exc:  # noqa: BLE001 — 注入边的任意故障统一映射来源不可达
        raise DomainError(ErrorCode.SOURCE_NOT_FOUND, f"{operation}: {_safe(location)}") from exc


def resolve_git_repo(location: str, *, cloner: Cloner | None = None) -> dict[str, Any]:
    """git-repo 来源：克隆到**临时工作区** → 读根目录 :data:`MANIFEST_FILENAME` → 清理。"""
    clone = cloner if cloner is not None else _clone_with_git
    with tempfile.TemporaryDirectory(prefix="core-plugin-") as tmp:
        dest = Path(tmp) / "repo"
        _normalize("仓库不可达", location, lambda: clone(location, dest))
        manifest_file = dest / MANIFEST_FILENAME
        if not manifest_file.is_file():
            raise DomainError(
                ErrorCode.SOURCE_NOT_FOUND,
                f"仓库缺少 {MANIFEST_FILENAME}: {_safe(location)}",
            )
        return _parse_manifest(manifest_file.read_bytes(), location)


def resolve_market_registry(location: str, *, fetcher: Fetcher | None = None) -> dict[str, Any]:
    """market-registry 来源：取 ``location`` 所指 manifest 文档（鉴权经 fetcher 携带）。"""
    fetch = fetcher if fetcher is not None else _http_json
    return _normalize("来源不可达", location, lambda: fetch(location))


def resolve_mcp_endpoint(location: str) -> dict[str, Any]:
    """mcp-endpoint 来源：由端点串**合成** manifest（解析期零网络）。

    端点可达性归 install 期 `MCPClient.add` 判定 —— 与 ``mcp add``「先连通验证再落盘」
    同一口径，避免「解析成功但装不上」的双重语义。
    """
    return {"name": default_endpoint_name(location), "url": location}
