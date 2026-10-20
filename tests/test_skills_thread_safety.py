"""0296 · 技能库跨线程安全。

后台收尾（观察者 / 维护）已移出事件循环线程：SOP 提炼在线程池里**写**技能库，
前台技能路由同时在**读**。`SkillLibrary` 若不加锁，`_persist` 迭代 `_skills` 时
另一线程注册新技能会触发 ``dictionary changed size during iteration``。

本文件用「慢速持久化 + 第二线程注册」把竞态窗口放大到确定可见：
持锁 ⇒ 第二个注册排队、两者都成功；无锁 ⇒ 迭代期被修改、注册抛错。
"""

from __future__ import annotations

import threading

import pytest

import core.skills.library as library_module
from core.skills import Skill, SkillLibrary

# 第二个技能（seed 之后的新注册）的持久化调用序号
_SECOND_PERSIST_CALL = 2


def _skill(skill_id: str) -> Skill:
    return Skill(skill_id=skill_id, description="并发注册样例")


def test_concurrent_register_is_serialized_against_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一个线程持久化途中，另一个线程的注册须等待，不得改写正在迭代的字典。"""
    library = SkillLibrary()
    library.register(_skill("skills.demo.seed"))

    real_asdict = library_module.asdict
    entered = threading.Event()
    release = threading.Event()
    calls = [0]

    def slow_asdict(obj: object) -> object:
        calls[0] += 1
        if calls[0] == _SECOND_PERSIST_CALL:  # 第二个技能持久化时暂停
            entered.set()
            assert release.wait(timeout=2.0), "测试未释放持久化窗口"
        return real_asdict(obj)

    monkeypatch.setattr(library_module, "asdict", slow_asdict)

    errors: list[BaseException] = []

    def register(skill_id: str) -> None:
        try:
            library.register(_skill(skill_id))
        except BaseException as err:  # noqa: BLE001 — 收集线程内异常回主线程断言
            errors.append(err)

    first = threading.Thread(target=register, args=("skills.demo.one",))
    second = threading.Thread(target=register, args=("skills.demo.two",))
    first.start()
    assert entered.wait(timeout=2.0), "第一个注册应已进入持久化"
    second.start()
    # 无锁时 second 会在此窗口内改写 `_skills`，令 first 的迭代抛 RuntimeError。
    release.set()
    first.join(timeout=2.0)
    second.join(timeout=2.0)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert {skill.skill_id for skill in library.all_skills()} == {
        "skills.demo.seed",
        "skills.demo.one",
        "skills.demo.two",
    }
