"""JSON 快照落盘（通用）。

运行态多为**可变快照**（技能字段被迭代改写、灰度状态被覆盖、样本组提炼后清空、观察窗口
累积样本），故用单文件 JSON 整体重写而非追加日志（对照 ``memory.jsonl`` / ``checkpoints.jsonl``
的追加日志语义）；各状态组件各持自己的 ``path`` 与序列化形状，只把「字节进字节出」交给本
模块的两个纯函数（标准库 JSON，零第三方依赖）。

本模块**不 import 任何能力包**（skills / evolution / memory …），只提供中性 IO；调用方
（技能态、进化观察态）负责自己的序列化。

未注入路径（``path=None``）不落盘；落盘缺失或损坏一律降级为 ``None``——调用方据此以空态
启动（这些是可重建的派生数据，不阻断启动）。

对应接口：doc/03-interfaces/skills-interface.md §7、doc/03-interfaces/evolution-interface.md §3.1
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
