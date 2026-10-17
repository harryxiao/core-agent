"""对话转录存储（memory）：按轮追加的对话原文日志。

**不是记忆层级**：转录是原始对话流（谁在何时说了什么），不参与温度分层检索、
排名、`reuse_count` 强化、压实、固化与遗忘，也**不**经 ``MemoryStore.read`` 取出 ——
只能经本模块按会话读取。这与 L4 归档层（遗忘/压实的下沉目标）是两回事。

落盘为 ``$CORE_STATE_DIR`` 下的**单文件** JSONL（单店 + `session_id` 列，与记忆同店
形态一致，不为每会话建独立存储实例）；写入用 ``os.open(O_APPEND)`` + 单次
``os.write`` 整行（POSIX 追加原子，跨进程并发追加不会写坏行）。

对应规格：doc/openspec/specs/memory/spec.md「对话转录持久化（非记忆层级）」
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, cast

from core.tokens import estimate_tokens

# 会话标题上限（派生读模型，不落盘）：`GET /sessions` 的 `title` 由此截断
_TITLE_LIMIT = 30


def _tokens(text: str) -> int:
    """与上下文/记忆读预算同一 CJK 感知口径（change 0245 / ADR-0233）。"""
    return estimate_tokens(text)


def _title(content: str) -> str:
    """标题：压平换行、截断至 `_TITLE_LIMIT`；超长补省略号。"""
    flat = " ".join(content.split())
    return flat if len(flat) <= _TITLE_LIMIT else flat[:_TITLE_LIMIT] + "…"


def _truncate_newest(rows: list[dict[str, Any]], max_tokens: int) -> list[dict[str, Any]]:
    """按 token 从新到旧截断；截断后丢弃开头的孤儿 assistant 行（其提问已被截掉）。

    `max_tokens <= 0` ⇒ 原样返回（不截断、不丢孤儿）。`tail` 与 `window` 共用同一语义，
    避免第二份真源。
    """
    if max_tokens <= 0:
        return list(rows)
    kept: list[dict[str, Any]] = []
    used = 0
    for entry in reversed(rows):
        cost = _tokens(str(entry.get("content", "")))
        if used + cost > max_tokens:
            break
        used += cost
        kept.append(entry)
    kept.reverse()
    while kept and kept[0].get("role") != "user":
        kept.pop(0)
    return kept


class TranscriptStore:
    """对话转录：按轮追加 + 按会话读取 + 派生摘要（`path=None` ⇒ 纯内存）。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 写 ----

    def append(
        self, session_id: str, role: str, content: str, *, created_at: float | None = None
    ) -> None:
        """追加一条转录；``session_id`` 为空串（未归属）时**不落盘**。"""
        if not session_id:
            return
        record: dict[str, Any] = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": time.time() if created_at is None else created_at,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            if self._path is None:
                self._entries.append(record)
                return
            fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)

    # ---- 读 ----

    def read(self, session_id: str) -> list[dict[str, Any]]:
        """该会话的全部转录（按追加次序）。"""
        return [e for e in self._all() if e.get("session_id") == session_id]

    def tail(self, session_id: str, turns: int, *, max_tokens: int = 0) -> list[dict[str, Any]]:
        """最近 `turns` 轮对话（轮 = 一条 user 提问及其答复）。

        `max_tokens` > 0 时再按 token 从新到旧截断；截断后若开头剩的是孤儿
        assistant 行（其提问已被截掉）则一并丢弃。`turns <= 0` ⇒ 空。
        """
        if turns <= 0:
            return []
        entries = self.read(session_id)
        starts = [i for i, e in enumerate(entries) if e.get("role") == "user"]
        if not starts:
            return []
        window = entries[starts[max(0, len(starts) - turns)] :]
        return _truncate_newest(window, max_tokens)

    def window(
        self,
        session_id: str,
        *,
        short_turns: int,
        mid_turns: int,
        short_tokens: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """三层滑窗切分：返回 `(短带原文, 中带原文)`（change 0178 / ADR-0169）。

        短带 = 末 `short_turns` 轮，经 `_truncate_newest`（丢最旧 + 丢孤儿 assistant）；
        中带 = 紧邻短带之前的 `mid_turns` 轮，**不截断**（由中层摘要承载）。两带**不重叠**；
        轮数不足时短带吃满、中带为空；`short_turns <= 0` ⇒ `([], [])`。
        """
        if short_turns <= 0:
            return [], []
        entries = self.read(session_id)
        starts = [i for i, e in enumerate(entries) if e.get("role") == "user"]
        if not starts:
            return [], []
        short_start = max(0, len(starts) - short_turns)
        short_rows = _truncate_newest(entries[starts[short_start] :], short_tokens)
        mid_start = max(0, short_start - mid_turns)
        mid_rows = (
            entries[starts[mid_start] : starts[short_start]] if mid_start < short_start else []
        )
        return short_rows, mid_rows

    def summaries(self) -> dict[str, dict[str, Any]]:
        """按会话的派生读模型：`{session_id: {title, updated_at}}`（未归属不入）。

        标题取该会话**首条用户消息**（截断）；`updated_at` 取最近一条转录时间戳。
        无用户消息的会话不伪造标题（`title` 为空串）。
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in self._all():
            session_id = str(entry.get("session_id", ""))
            if session_id:
                grouped.setdefault(session_id, []).append(entry)
        result: dict[str, dict[str, Any]] = {}
        for session_id, entries in grouped.items():
            first_user = next((e for e in entries if e.get("role") == "user"), None)
            result[session_id] = {
                "title": "" if first_user is None else _title(str(first_user.get("content", ""))),
                "updated_at": max(float(e.get("created_at", 0.0)) for e in entries),
            }
        return result

    # ---- 内部 ----

    def _all(self) -> list[dict[str, Any]]:
        """全部转录条目；坏行跳过、缺文件按空（降级不抛错、不阻断主流程）。"""
        path = self._path
        if path is None:
            return list(self._entries)
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and "session_id" in record and "role" in record:
                entries.append(cast("dict[str, Any]", record))
        return entries
