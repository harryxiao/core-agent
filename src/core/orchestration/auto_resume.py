"""未完成任务自动续跑的有界退避状态（change 0278 / ADR-0268）。

自动续跑**缺省关闭**（`orchestration.auto_resume`）；开启后 `task` 入口在起新任务前扫描
检查点，对 `done=false` 的编排任务按检查点重建并续跑。与手动 `--resume` 不同，自动路径必须
跨进程有界 —— 进程内的 `FAILED` 是终态（同一调度器无法原地重试），所以尝试次数与上次尝试
时间落盘在 `$CORE_STATE_DIR/auto-resume.json`：

- 首次即到期；第 n 次尝试后按 ``min(60·2**(n-1), 3600)`` 秒退避；
- 累计 ``AUTO_RESUME_MAX_ATTEMPTS`` 次后不再自动尝试（`task --resume-all` 显式入口不受限）；
- 成功续跑即清零；状态文件损坏 ⇒ 告警后按空状态处理（自动续跑是尽力而为，不阻断入口）。

状态文件只含 task id / 计数 / 时间戳，不落任务正文与任何密钥。
"""

from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Any, cast

AUTO_RESUME_MAX_ATTEMPTS = 3
AUTO_RESUME_BASE_DELAY_S = 60.0
AUTO_RESUME_MAX_DELAY_S = 3600.0


class AutoResumeState:
    """跨进程的自动续跑尝试账本（原子写、0600、损坏容忍）。"""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._warned_persist = False
        self._data: dict[str, dict[str, Any]] = self._load()

    def due(self, task_id: str, *, now: float | None = None) -> bool:
        """该任务是否已可再次自动尝试（未达上限且已过退避窗口）。"""
        record = self._data.get(task_id)
        if record is None:
            return True
        attempts = int(record.get("attempts", 0))
        if attempts >= AUTO_RESUME_MAX_ATTEMPTS:
            return False
        last_ts = float(record.get("last_ts", 0.0))
        current = time.time() if now is None else now
        return current - last_ts >= _delay_s(attempts)

    def record_attempt(self, task_id: str, *, now: float | None = None) -> None:
        """记一次尝试（**执行前**调用：进程若中途崩溃也已计入上限）。"""
        attempts = self.attempts(task_id) + 1
        self._data[task_id] = {
            "attempts": attempts,
            "last_ts": time.time() if now is None else now,
        }
        self._save()

    def clear(self, task_id: str) -> None:
        """续跑成功：清零该任务。"""
        if self._data.pop(task_id, None) is not None:
            self._save()

    def retain(self, task_ids: set[str]) -> None:
        """只保留仍然未完成的任务（已消失的任务不长期占账本）。"""
        stale = set(self._data) - task_ids
        if not stale:
            return
        for task_id in stale:
            del self._data[task_id]
        self._save()

    def attempts(self, task_id: str) -> int:
        record = self._data.get(task_id)
        return int(record.get("attempts", 0)) if record is not None else 0

    # ---- 内部 ----

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            warnings.warn(
                f"自动续跑状态文件损坏，按空状态处理: {self._path.name}",
                stacklevel=2,
            )
            return {}
        if not isinstance(raw, dict):
            warnings.warn(
                f"自动续跑状态文件损坏，按空状态处理: {self._path.name}",
                stacklevel=2,
            )
            return {}
        data: dict[str, dict[str, Any]] = {}
        for task_id, record in cast(dict[str, Any], raw).items():
            if not isinstance(record, dict):
                continue
            entry = cast(dict[str, Any], record)
            attempts = entry.get("attempts")
            last_ts = entry.get("last_ts")
            if not isinstance(attempts, int) or not isinstance(last_ts, (int, float)):
                continue
            data[str(task_id)] = {"attempts": attempts, "last_ts": float(last_ts)}
        return data

    def _save(self) -> None:
        if not self._data:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                self._warn_persist()
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except OSError:
            self._warn_persist()

    def _warn_persist(self) -> None:
        if self._warned_persist:
            return
        self._warned_persist = True
        warnings.warn(f"自动续跑状态无法落盘（仅本进程内有效）: {self._path.name}", stacklevel=2)


def _delay_s(attempts: int) -> float:
    """已做 ``attempts`` 次后的退避（60s 起指数翻倍，封顶 3600s）。"""
    return min(AUTO_RESUME_BASE_DELAY_S * (2.0 ** max(0, attempts - 1)), AUTO_RESUME_MAX_DELAY_S)
