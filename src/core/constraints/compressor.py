"""上下文压缩中间件（constraints）。

丢弃对话历史中的已完成子任务与重复内容，保留关键约束（system）与未决事项，
对抗上下文信息腐烂。

对应规格：doc/openspec/specs/constraints/spec.md（上下文压缩中间件）
"""

from __future__ import annotations

from typing import Any

_DONE_MARKERS = ("[已完成]", "[done]")


def _is_completed(content: str) -> bool:
    return any(marker in content for marker in _DONE_MARKERS)


class ContextCompressor:
    """按规则清理冗余上下文消息。"""

    def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """丢弃已完成 / 重复消息，保留关键约束与未决事项。"""
        seen: set[tuple[str, str]] = set()
        kept: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
            if role != "system" and _is_completed(content):
                continue
            key = (role, content)
            if key in seen:
                continue
            seen.add(key)
            kept.append(message)
        return kept
