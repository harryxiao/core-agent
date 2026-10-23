"""上下文淘汰的情景检查点纯函数（context，change 0310 / ADR-0300）。

被淘汰（滑出保留窗口）的转录行在回写为 ``context_checkpoint`` 情景记录时，正文取
**确定性抽取式摘要**：头部水位行 + 逐行 ``role: content``；写前脱敏、总长与单行均有界。
原文不复制进记忆 —— 转录日志仍是原文真源（SDD §4.5 / §6.7 Tier 3）。

本模块无 I/O、无状态：便于单测与复用。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, cast

from core.memory import redact_secrets
from core.memory.transcript import CHECKPOINT_ID_PREFIX, CHECKPOINT_TAG

__all__ = [
    "CHECKPOINT_ID_PREFIX",
    "CHECKPOINT_TAG",
    "MAX_CHECKPOINT_ARTIFACTS",
    "MAX_CHECKPOINT_CHARS",
    "MAX_CHECKPOINT_LINE_CHARS",
    "MAX_ARTIFACT_CHARS",
    "MAX_ROW_ARTIFACTS",
    "checkpoint_artifacts",
    "checkpoint_summary",
]

# 摘要上界：总长 800 字符、单行 120 字符（换行压平后截断，尾部补省略号）
MAX_CHECKPOINT_CHARS = 800
MAX_CHECKPOINT_LINE_CHARS = 120
# 工件引用：被淘汰区间总计 16 条、单路径 200 字符
MAX_CHECKPOINT_ARTIFACTS = 16
MAX_ROW_ARTIFACTS = 8
MAX_ARTIFACT_CHARS = 200


def _row_content(row: dict[str, Any]) -> str:
    """单行正文 → 换行压平、脱敏、截断至单行上界。"""
    flat = " ".join(str(row.get("content", "")).split())
    flat = redact_secrets(flat)
    if len(flat) <= MAX_CHECKPOINT_LINE_CHARS:
        return flat
    return flat[: MAX_CHECKPOINT_LINE_CHARS - 1] + "…"


def checkpoint_summary(rows: Sequence[dict[str, Any]], *, seq_from: int, seq_to: int) -> str:
    """淘汰区间 → 确定性摘要（头部水位行 + 逐行 ``role: content``，总长 ≤ 800）。"""
    header = f"会话检查点 seq {seq_from}-{seq_to}（{len(rows)} 行）"
    lines = [header]
    used = len(header)
    truncated = False
    for row in rows:
        line = f"- {row.get('role', 'unknown')}: {_row_content(row)}"
        cost = len(line) + 1  # 含换行
        if used + cost > MAX_CHECKPOINT_CHARS:
            truncated = True
            break
        lines.append(line)
        used += cost
    if truncated:
        tail = f"…（共 {len(rows)} 行，已截断）"
        if used + len(tail) + 1 > MAX_CHECKPOINT_CHARS and len(lines) > 1:
            lines.pop()
        lines.append(tail)
    return "\n".join(lines)


def checkpoint_artifacts(rows: Iterable[dict[str, Any]]) -> list[str]:
    """聚合被淘汰区间的 ``artifacts`` 列：去重保序、单路径与总计均有界。"""
    seen: dict[str, None] = {}
    for row in rows:
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        for item in cast("list[Any]", artifacts):
            if not isinstance(item, str) or not item:
                continue
            path = item[:MAX_ARTIFACT_CHARS]
            seen.setdefault(path, None)
            if len(seen) >= MAX_CHECKPOINT_ARTIFACTS:
                return list(seen)
    return list(seen)
