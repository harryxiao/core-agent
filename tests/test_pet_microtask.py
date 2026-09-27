"""pet-microtask 单元测试（只执行已启用任务，侵入性可配置关闭）。"""

from __future__ import annotations

from core.pet.microtask import MicrotaskRunner


def test_default_excludes_intrusive() -> None:
    assert "nonsense_comment" not in MicrotaskRunner().enabled_tasks()


def test_intrusive_enabled_by_flag() -> None:
    assert "nonsense_comment" in MicrotaskRunner(intrusive=True).enabled_tasks()


def test_run_known_task_deterministic() -> None:
    runner = MicrotaskRunner()
    assert runner.run("terminal_walk") is not None
    assert runner.run("system_hint") is not None


def test_run_disabled_task_returns_none() -> None:
    assert MicrotaskRunner().run("nonsense_comment") is None


def test_intrusive_task_writes_comment() -> None:
    written: list[str] = []
    runner = MicrotaskRunner(intrusive=True, comment_writer=written.append)
    assert runner.run("nonsense_comment") is not None
    assert written == ["给代码加了一条无厘头注释。"]
