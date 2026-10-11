"""记忆后端落盘耐久端到端（change 0206 / 台账 E143）。

既有 ``tests/test_memory_backend.py`` 覆盖正常读写路径；本文件补规格「记忆后端落盘耐久」
四项承诺、而此前**无处验证**的事：

① **写入原子性**：持久化写入中途被中断（半写）SHALL NOT 损坏既有条目集合 —— 旧实现
   ``Path.write_text``（先截断再整写）会**整体丢失**；
② **坏行容错**：半行/结构不符行 SHALL 被跳过并告警（只报计数），SHALL NOT 阻断启动 ——
   旧实现 ``MemoryEntry(**json.loads(line))`` 直接抛异常 ⇒ 客户端起不来；
③ **完好文件零回归**：重载 → 再持久化，字节逐字节不变；
④ **真实进程崩溃**：子进程写入后被 ``SIGKILL``，另进程重载无半写残留（镜像
   ``tests/test_durability_crash.py`` 的真崩溃口径）。
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import warnings

import pytest

from core.memory import FileBackend, MemoryEntry

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

# 子进程脚本：写两条记忆后 SIGKILL 自杀（无清理、无 flush 机会）。
_CHILD = """
import os, signal, sys
from pathlib import Path

from core.memory import FileBackend, MemoryEntry

backend = FileBackend(Path(sys.argv[1]))
for i in range(2):
    backend.put(
        MemoryEntry(
            id=f"e{i}", layer="L2", content=f"内容{i}", tags=["t"], source="loop", trace_id="t"
        )
    )
os.kill(os.getpid(), signal.SIGKILL)
"""


def _entry(i: int) -> MemoryEntry:
    return MemoryEntry(
        id=f"e{i}", layer="L2", content=f"内容{i}", tags=["t"], source="loop", trace_id="t"
    )


# ---- ① 写入原子性（半写不损坏既有条目） ----


def test_interrupted_persist_keeps_existing_entries(tmp_path, monkeypatch) -> None:
    """写入中断（写到一半）→ 重载后既有条目完好。

    以「先截断写目标再抛 OSError」模拟进程在写入中途被终止（镜像
    test_durability_crash.test_interrupted_persist_keeps_existing_checkpoints 的确定性性质测试）：
    失败点若落在真文件上，既有条目即整体丢失。
    """
    path = tmp_path / "memory.jsonl"
    backend = FileBackend(path)
    backend.put(_entry(0))
    raw_before = path.read_text(encoding="utf-8")
    assert raw_before.strip()

    def _half_write(self: pathlib.Path, *_args: object, **_kwargs: object) -> int:
        self.open("w").close()  # 截断（半写已落盘的部分）
        raise OSError("进程在写入中途被终止")

    monkeypatch.setattr(pathlib.Path, "write_text", _half_write)
    with pytest.raises(OSError):
        backend.put(_entry(1))
    monkeypatch.undo()

    assert path.read_text(encoding="utf-8") == raw_before  # 目标文件未被触碰
    reloaded = FileBackend(path)
    assert [e.id for e in reloaded.search("")] == ["e0"]


# ---- ② 坏行容错（跳过 + 告警计数，不阻断启动） ----


def test_corrupt_lines_skipped_with_warning(tmp_path) -> None:
    """半行（非法 JSON）与结构不符行（合法 JSON 非条目形状）→ 跳过、告警只报计数、好行俱在。"""
    path = tmp_path / "memory.jsonl"
    backend = FileBackend(path)
    backend.put(_entry(0))
    backend.put(_entry(1))
    good_line = path.read_text(encoding="utf-8").splitlines()[0]

    path.write_text(
        good_line
        + "\n"  # 完好行
        + '{"id": "half", "layer": "L2", "cont'
        + "\n"  # 半行：非法 JSON
        + '{"foo": 1}'
        + "\n",  # 结构不符：MemoryEntry(**) 抛 TypeError
        encoding="utf-8",
    )
    with pytest.warns(UserWarning, match=r"2 条损坏行"):
        reloaded = FileBackend(path)
    assert [e.id for e in reloaded.search("")] == ["e0"]


def test_warning_does_not_echo_content(tmp_path) -> None:
    """告警只含计数与文件名，不含损坏行正文（条目可能含敏感内容）。"""
    path = tmp_path / "memory.jsonl"
    path.write_text('{"id": "x", "SECRET-CANARY": true}\n', encoding="utf-8")
    with pytest.warns(UserWarning) as records:
        FileBackend(path)
    message = str(records[0].message)
    assert "SECRET-CANARY" not in message
    assert "1 条损坏行" in message


# ---- ③ 完好文件零回归（往返逐字节不变） ----


def test_roundtrip_bytes_identical(tmp_path) -> None:
    """完好文件重载 → 覆盖式重写（put 既有 id 不改集合序）⇒ 字节逐字节不变。"""
    path = tmp_path / "memory.jsonl"
    backend = FileBackend(path)
    for i in range(3):
        backend.put(_entry(i))
    raw = path.read_text(encoding="utf-8")

    reloaded = FileBackend(path)
    assert [e.id for e in reloaded.search("")] == ["e0", "e1", "e2"]
    reloaded.put(_entry(0))  # 触发一次持久化（集合不变）
    assert path.read_text(encoding="utf-8") == raw


# ---- ④ 真实进程 SIGKILL 后重载可读 ----


def test_real_sigkill_then_reload(tmp_path) -> None:
    """真进程被杀 → 另进程重载：条目全在、无告警（原子替换 ⇒ 无半写残留）。"""
    path = tmp_path / "memory.jsonl"
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    proc = subprocess.run([sys.executable, "-c", _CHILD, str(path)], env=env, check=False)
    assert proc.returncode == -signal.SIGKILL  # 确系被信号杀死，非正常退出

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 任何告警都转为失败（原子 ⇒ 应无告警）
        reloaded = FileBackend(path)
    assert [e.id for e in reloaded.search("")] == ["e0", "e1"]
