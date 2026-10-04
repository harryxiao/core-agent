"""技能态落盘（skill state persistence）。

技能态是**可变快照**（技能字段会被迭代改写、灰度状态会被覆盖、样本组提炼后清空），
故用单文件 JSON 整体重写而非追加日志；四个状态组件（技能库 / 执行反馈 / SOP 样本 /
灰度·A-B）各持自己的 ``path`` 与序列化形状，只把「字节进字节出」交给本模块的两个
纯函数（标准库 JSON，零第三方依赖）。

未注入路径（``path=None``）不落盘；落盘缺失或损坏一律降级为 ``None``——调用方据此
以空态启动（技能态是可重建的派生数据，不阻断启动）。

对应接口：doc/03-interfaces/skills-interface.md §7
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def read_state(path: Path | None) -> Any:
    """读快照；``None`` / 文件缺失 / 非法 JSON → ``None``（不抛）。"""
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_state(path: Path | None, data: Any) -> None:
    """原子写快照（同目录临时文件 + ``os.replace``）；``None`` → 不写盘。"""
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
