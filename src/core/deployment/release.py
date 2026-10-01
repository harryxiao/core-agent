"""发布与升级（deployment）。

版本化发布 + 滚动升级 + 回滚：升级失败自动回滚到上一可用版本，运行环境不处于
半升级状态。升级/回滚成败经注入 apply 回调判定。

对应接口：doc/03-interfaces/deployment-interface.md §3
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from .errors import DeploymentError, DeploymentErrorCode
from .models import HealthStatus, ReleaseInfo


class ReleaseManager:
    """版本化发布 + 升级 / 回滚。"""

    def __init__(
        self,
        *,
        apply: Callable[[str], HealthStatus] | None = None,
        path: Path | None = None,
    ) -> None:
        self._apply: Callable[[str], HealthStatus] = (
            apply if apply is not None else lambda _version: HealthStatus(alive=True)
        )
        self._releases: dict[str, ReleaseInfo] = {}
        self._current: str | None = None
        self._previous: str | None = None
        self._path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                self._load()

    @property
    def current(self) -> str | None:
        """当前生效版本。"""
        return self._current

    def publish(self, release: ReleaseInfo) -> str:
        """版本化发布，返回可寻址版本引用。"""
        self._releases[release.version] = release
        if self._current is None:
            self._current = release.version
        self._persist()
        return release.version

    def upgrade(self, version: str) -> None:
        """滚动升级到目标版本；失败自动回滚并抛 UPGRADE_FAILED。"""
        if version not in self._releases:
            raise DeploymentError(
                DeploymentErrorCode.UPGRADE_FAILED,
                f"版本 {version} 不存在",
            )
        if version == self._current:
            return
        self._previous = self._current
        self._current = version
        if not self._apply(version).alive:
            self.rollback()
            raise DeploymentError(
                DeploymentErrorCode.UPGRADE_FAILED,
                f"升级到 {version} 失败，已回滚到 {self._current}",
            )
        self._persist()

    def rollback(self) -> None:
        """回滚到上一可用版本；失败抛 ROLLBACK_FAILED。"""
        if self._previous is None:
            raise DeploymentError(
                DeploymentErrorCode.ROLLBACK_FAILED,
                "无可用回滚版本",
            )
        target = self._previous
        self._previous = None
        if not self._apply(target).alive:
            raise DeploymentError(
                DeploymentErrorCode.ROLLBACK_FAILED,
                f"回滚到 {target} 失败",
            )
        self._current = target
        self._persist()

    # ---- 持久化 ----

    def _persist(self) -> None:
        if self._path is None:
            return
        data = {
            "current": self._current,
            "previous": self._previous,
            "releases": {v: asdict(r) for v, r in self._releases.items()},
        }
        self._path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        if self._path is None:
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._current = data.get("current")
        self._previous = data.get("previous")
        self._releases = {
            version: ReleaseInfo(**info) for version, info in data.get("releases", {}).items()
        }
