"""notes 包内部的私有落盘助手：0600 + 原子替换（候选区 / 回收目录共用）。

故意不 import ``core.orchestration``：notes 是 L2 底座，不向上依赖编排层；
与 ``orchestration.state_files`` 的 0600 口径保持一致即可（不共享实现）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_private_text(path: Path, text: str) -> None:
    """原子写文本：临时文件 → chmod 0600 → ``os.replace``（中断不留半截目标文件）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def write_private_json(path: Path, data: Any) -> None:
    """原子写 JSON（0600）；``ensure_ascii=False`` 保留中文可读性。"""
    write_private_text(path, json.dumps(data, ensure_ascii=False, indent=2))
