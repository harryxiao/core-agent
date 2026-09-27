"""制品发布（ci-cd）。

门禁通过的交付打包为版本化制品进入发布通道；制品可追溯、可回滚。
发布通道可注入（默认离线未接，抛 CHANNEL_UNREACHABLE）。

对应接口：doc/03-interfaces/ci-cd-interface.md §3
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from .errors import CiCdError, CiCdErrorCode
from .models import Artifact, PipelineRun


def _default_channel(artifact: Artifact) -> None:
    """生产发布通道：真实制品仓库未接。"""
    raise CiCdError(
        CiCdErrorCode.CHANNEL_UNREACHABLE,
        f"发布通道不可达（制品 {artifact.version} 需接真实制品仓库）",
    )


class ArtifactPublisher:
    """版本化制品发布 / 回滚。"""

    def __init__(self, *, channel: Callable[[Artifact], None] | None = None) -> None:
        self._channel = channel if channel is not None else _default_channel
        self._artifacts: dict[str, Artifact] = {}
        self._counter = 0

    def publish(self, run: PipelineRun) -> Artifact:
        """门禁通过的交付打包为带版本号制品，进入发布通道。"""
        if run.status != "passed":
            raise CiCdError(CiCdErrorCode.GATE_FAILED, "门禁未通过，无法发布制品")
        self._counter += 1
        version = f"v{self._counter}.0.0"
        artifact = Artifact(
            artifact_id=uuid.uuid4().hex,
            version=version,
            commit_ref=run.commit_ref,
            channel="release",
        )
        self._channel(artifact)
        self._artifacts[version] = artifact
        return artifact

    def rollback(self, version: str) -> Artifact:
        """回滚到指定历史版本；版本不存在抛 ARTIFACT_NOT_FOUND。"""
        artifact = self._artifacts.get(version)
        if artifact is None:
            raise CiCdError(CiCdErrorCode.ARTIFACT_NOT_FOUND, f"制品版本 {version} 不存在")
        return artifact
