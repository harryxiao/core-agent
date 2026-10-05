"""pet-microtask 单元测试（只执行已启用任务；微任务产出必须**真实**，否则不报）。

change 0087 / 账本 E26：三条任务各自有真实来源（命令历史条数 / 真实负载 / 真实写回），
**无真实产出 ⇒ 返回 `None`**（SHALL NOT 投出预制文案谎报）；`terminal_walk` 只报**条数**，
绝不外泄命令历史内容。
"""

from __future__ import annotations

from pathlib import Path

from core.pet.microtask import MicrotaskRunner
from core.pet.microtask.microtask import _read_terminal_history, _system_hint


def test_default_excludes_intrusive() -> None:
    assert "nonsense_comment" not in MicrotaskRunner().enabled_tasks()


def test_intrusive_enabled_by_flag() -> None:
    assert "nonsense_comment" in MicrotaskRunner(intrusive=True).enabled_tasks()


def test_run_known_task_deterministic() -> None:
    """指定 task_id 确定性执行；探针可注入 ⇒ 不受运行环境影响。"""
    runner = MicrotaskRunner(walk_probe=lambda: 3, hint_probe=lambda: "系统提示")
    assert runner.run("terminal_walk") is not None
    assert runner.run("system_hint") == "系统提示"


def test_run_disabled_task_returns_none() -> None:
    assert MicrotaskRunner().run("nonsense_comment") is None


def test_intrusive_task_writes_comment() -> None:
    written: list[str] = []
    runner = MicrotaskRunner(intrusive=True, comment_writer=written.append)
    assert runner.run("nonsense_comment") is not None
    assert written == ["给代码加了一条无厘头注释。"]


def test_intrusive_task_without_writer_returns_none() -> None:
    """无写回口 ⇒ 无真实产出 ⇒ 不产出（不谎报）。"""
    assert MicrotaskRunner(intrusive=True).run("nonsense_comment") is None


# ---- terminal_walk：只报条数，绝不外泄内容 ----


def test_terminal_walk_reports_count_only(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.write_text("ls\ncd /tmp\n\nsecret-token\n", encoding="utf-8")
    count = _read_terminal_history(path=history)
    assert count == 3  # noqa: PLR2004 — 3 非空行（空行不计）
    out = MicrotaskRunner(walk_probe=lambda: count).run("terminal_walk")
    assert out is not None and "3" in out
    assert "secret-token" not in out, "绝不外泄命令历史内容"


def test_terminal_walk_unreadable_returns_none(tmp_path: Path) -> None:
    assert _read_terminal_history(path=tmp_path / "missing") is None


def test_terminal_walk_blank_history_returns_none(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.write_text("\n \n\n", encoding="utf-8")
    assert _read_terminal_history(path=history) is None


def test_terminal_walk_without_real_output_stays_silent() -> None:
    """探测无产出 ⇒ 任务返回 None（不报）。"""
    assert MicrotaskRunner(walk_probe=lambda: None).run("terminal_walk") is None


# ---- system_hint：真实负载，不显著则不出声 ----


def test_system_hint_reports_when_load_significant() -> None:
    out = _system_hint(loadavg=9.0, cpus=4)
    assert out is not None and "9" in out


def test_system_hint_silent_when_load_insignificant() -> None:
    assert _system_hint(loadavg=0.2, cpus=4) is None
