"""记忆治理审计日志（change 0308 / ADR-0298）。

append-only JSONL 旁路：只记**元数据**（不含正文），字符串字段先脱敏再截断；写入失败
fail-open（每实例告警一次，不阻断记忆操作）。读取面供 `memory audit` 使用，坏行跳过。
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import warnings
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from .extract import redact_secrets
from .protocol import MemoryEntry

# 单行字段上界（change 0308）：元数据也可能夹带密钥形态或超长 id；保证一行 ~1KB 以内。
_MAX_ID = 128
_MAX_FIELD = 128
_MAX_REASON = 64
_MAX_TARGET = 512
_MAX_FORMAT = 16
_MAX_HASH = 80


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _bounded(value: str, limit: int) -> str:
    """先脱敏再截断（避免明文跨越截断边界）。"""
    return _truncate(redact_secrets(value), limit)


class MemoryAuditLog:
    """治理审计日志（可选接线；``path=None`` ⇒ 全部 no-op）。"""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._warned = False

    @property
    def path(self) -> Path | None:
        return self._path

    def record(  # noqa: PLR0913 — 事件字段均为可选关键字，调用面清晰优先
        self,
        op: str,
        entry: MemoryEntry | None = None,
        *,
        reason: str = "",
        count: int | None = None,
        target: str = "",
        format: str = "",
    ) -> None:
        """追加一条治理事件；``entry`` 为空 ⇒ 只记动作级字段（如 export）。"""
        if self._path is None:
            return
        row = {
            "ts": time.time(),
            "op": _bounded(op, _MAX_FIELD),
            "id": _bounded(entry.id, _MAX_ID) if entry is not None else "",
            "layer": _bounded(entry.layer, _MAX_FIELD) if entry is not None else "",
            "kind": _bounded(entry.kind, _MAX_FIELD) if entry is not None else "",
            "source": _bounded(entry.source, _MAX_FIELD) if entry is not None else "",
            "session_id": _bounded(entry.session_id, _MAX_FIELD) if entry is not None else "",
            "trace_id": _bounded(entry.trace_id, _MAX_FIELD) if entry is not None else "",
            # 哈希是派生摘要（不含内容），只截断不脱敏 —— 脱敏会破坏「删除 / 导出」关联。
            "content_hash": _truncate(entry.content_hash, _MAX_HASH) if entry is not None else "",
            "reason": _bounded(reason, _MAX_REASON),
            "count": count,
            "target": _bounded(target, _MAX_TARGET),
            "format": _bounded(format, _MAX_FORMAT),
        }
        self._append(json.dumps(row, ensure_ascii=False) + "\n")

    def _append(self, line: str) -> None:
        """单次 ``os.write`` 整行（对齐 `memory-deleted.jsonl` / 转录的追加口径）。"""
        path = self._path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
            with contextlib.suppress(OSError):  # 追加到既有宽权限文件时一并收紧
                os.chmod(path, 0o600)
        except OSError as exc:
            if not self._warned:
                self._warned = True
                warnings.warn(
                    f"memory audit append failed ({exc.__class__.__name__}); "
                    "memory operations continue",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def read(self, limit: int | None = 50) -> list[dict[str, Any]]:
        """按文件序返回至多 ``limit`` 行（``None`` / ``0`` = 全部）；坏行跳过。"""
        if self._path is None:
            return []
        rows: deque[dict[str, Any]] = deque(maxlen=limit if limit and limit > 0 else None)
        try:
            with self._path.open(encoding="utf-8") as handle:
                _collect(handle, rows)
        except OSError:
            return []
        return list(rows)


def _collect(lines: Iterable[str], sink: deque[dict[str, Any]]) -> None:
    for line in lines:
        row = _parse_line(line)
        if row is not None:
            sink.append(row)


def _parse_line(line: str) -> dict[str, Any] | None:
    """单行解析：坏行与非对象行返回 ``None``（读取面容错）。"""
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, Any]", row) if isinstance(row, dict) else None
