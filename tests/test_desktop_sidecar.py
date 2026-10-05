"""桌面 sidecar 拉起（change 0100，账本 C8 代码半）。

规格「桌面打包」要求桌面壳自动拉起本地后端：sidecar SHALL 以**本地后端进程**形式 spawn
（argv 逐项传递、不经 shell、与拉起方同解释器），失败 SHALL 以结构化错误报告而非静默成功。
本文件不真起服务（真起会让单测挂住）：用 `Popen` 替身断言 argv，另用 `--help` 子进程证明
`python -m core.entry` 这个调用面**真的可用**。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import core.entry
from core.ui import UIAPILayer, UiError, UiErrorCode
from core.ui.desktop_bridge import DesktopBridge

_CALLS: list[tuple[list[str], dict[str, Any]]] = []


class _FakePopen:
    """记录 argv/kwargs 的 Popen 替身。"""

    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        _CALLS.append((argv, kwargs))


def test_sidecar_spawns_backend_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """spawn 参数逐项传递、不经 shell、用**本进程同解释器**（venv 下 `python` 未必同一个）。"""
    _CALLS.clear()
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)

    DesktopBridge(api=UIAPILayer(), port=8123).start_sidecar()

    argv, kwargs = _CALLS[0]
    assert argv == [
        sys.executable,
        "-m",
        "core.entry",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "8123",
    ]
    assert kwargs.get("shell", False) is False


def test_sidecar_spawn_failure_is_reported_not_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """可执行体缺失 ⇒ 结构化错误码，不静默成功（否则用户以为桌面起好了）。"""

    def _boom(argv: list[str], **kwargs: Any) -> Any:
        raise OSError("no such file")  # noqa: TRY003 — 模拟可执行体缺失，非业务报错

    monkeypatch.setattr(subprocess, "Popen", _boom)

    with pytest.raises(UiError) as exc:
        DesktopBridge(api=UIAPILayer()).start_sidecar()
    assert exc.value.code is UiErrorCode.UI_SIDECAR_FAILED


def test_entry_is_runnable_as_sidecar_target() -> None:
    """`python -m core.entry` 须可直接运行（缺 `__main__` 守卫即起不来）。"""
    env = {**os.environ, "PYTHONPATH": str(Path(core.entry.__file__).resolve().parents[1])}
    proc = subprocess.run(  # noqa: S603 — 固定 argv、无 shell、被测对象即本仓 CLI
        [sys.executable, "-m", "core.entry", "serve", "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--port" in proc.stdout
