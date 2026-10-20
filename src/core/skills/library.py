"""原子技能库（SkillLibrary）。

维护技能注册表 + 领域索引：注册时校验 schema（非法抛 INVALID_SKILL_SCHEMA），
前置条件不满足拒绝调用（返回 False 供调用方携带 PRECONDITION_FAILED）；
另提供 ``draft → active`` 的**显式启用**路径（skillhub 下载恒 draft，此前无路可出）。

技能库可落盘（注入 ``path``）：注册 / 卸载 / 启用即落盘、启动即恢复；缺省 ``path=None`` 纯内存。

对应接口：doc/03-interfaces/skills-interface.md §2
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.persistence import read_state, write_state
from core.plugin_registry import Effect, EffectTracker

from .errors import SkillError, SkillErrorCode
from .models import (
    MAX_DESCRIPTION_CHARS,
    MAX_INSTRUCTIONS_CHARS,
    MAX_PRECONDITION_CHARS,
    MAX_PRECONDITIONS,
    MAX_SKILL_ID_CHARS,
    MAX_TASK_TYPE_CHARS,
    MAX_TASK_TYPES,
    Skill,
)

# 启用效应按此 trace 登记（回滚即恢复启用前状态）
_ACTIVATE_TRACE = "skills.activate"

# 退役效应按此 trace 登记（回滚即恢复退役前状态）
_DEPRECATE_TRACE = "skills.deprecate"


def _domain(skill_id: str) -> str:
    """从 "skills.<domain>.<name>" 提取领域段。"""
    parts = skill_id.split(".")
    return parts[1] if len(parts) > 1 else ""


def _check_bounds(skill: Skill) -> None:
    """字段上界校验（change 0255 / ADR-0246）：越界 ⇒ INVALID_SKILL_SCHEMA。

    错误文案只报字段名与上界，**绝不回显字段内容**（instructions 可能复述明文密钥）。
    """
    scalar_bounds = (
        ("skill_id", len(skill.skill_id), MAX_SKILL_ID_CHARS),
        ("instructions", len(skill.instructions), MAX_INSTRUCTIONS_CHARS),
        ("description", len(skill.description), MAX_DESCRIPTION_CHARS),
    )
    for name, size, limit in scalar_bounds:
        if size > limit:
            raise SkillError(
                SkillErrorCode.INVALID_SKILL_SCHEMA,
                f"技能 {skill.skill_id} {name} 超长（{size} > {limit}）",
            )
    if len(skill.task_types) > MAX_TASK_TYPES:
        raise SkillError(
            SkillErrorCode.INVALID_SKILL_SCHEMA,
            f"技能 {skill.skill_id} task_types 超量（{len(skill.task_types)} > {MAX_TASK_TYPES}）",
        )
    if any(len(item) > MAX_TASK_TYPE_CHARS for item in skill.task_types):
        raise SkillError(
            SkillErrorCode.INVALID_SKILL_SCHEMA,
            f"技能 {skill.skill_id} task_type 超长（≤{MAX_TASK_TYPE_CHARS}）",
        )
    if len(skill.preconditions) > MAX_PRECONDITIONS:
        raise SkillError(
            SkillErrorCode.INVALID_SKILL_SCHEMA,
            f"技能 {skill.skill_id} preconditions 超量"
            f"（{len(skill.preconditions)} > {MAX_PRECONDITIONS}）",
        )
    if any(len(item) > MAX_PRECONDITION_CHARS for item in skill.preconditions):
        raise SkillError(
            SkillErrorCode.INVALID_SKILL_SCHEMA,
            f"技能 {skill.skill_id} precondition 超长（≤{MAX_PRECONDITION_CHARS}）",
        )


class SkillLibrary:
    """原子技能库：注册 / 检索 / 前置条件检查。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._skills: dict[str, Skill] = {}
        self._domain_index: dict[str, list[str]] = {}
        # 线程安全（change 0296）：后台收尾已移出事件循环线程，SOP 提炼（写）与前台技能
        # 路由（读）会并发访问同一库；RLock 覆盖注册 / 查询 / 启停 / 删除 / 持久化 / 索引。
        self._lock = threading.RLock()
        self._load()

    def register(self, skill: Skill) -> None:
        """入库；schema 非法或字段越界抛 INVALID_SKILL_SCHEMA。"""
        if not skill.skill_id:
            raise SkillError(SkillErrorCode.INVALID_SKILL_SCHEMA, "skill_id 不能为空")
        if not isinstance(skill.param_schema, dict):
            raise SkillError(
                SkillErrorCode.INVALID_SKILL_SCHEMA,
                f"技能 {skill.skill_id} param_schema 非法（须为 dict）",
            )
        _check_bounds(skill)
        with self._lock:
            self._skills[skill.skill_id] = skill
            self._index(skill)
            self._persist()

    def lookup(self, skill_id: str) -> Skill:
        """按 skill_id 精确检索。"""
        with self._lock:
            return self._skills[skill_id]

    def list_by_domain(self, domain: str) -> list[Skill]:
        """按领域列出技能。"""
        with self._lock:
            return [self._skills[sid] for sid in self._domain_index.get(domain, [])]

    def all_skills(self) -> list[Skill]:
        """返回全部已注册技能。"""
        with self._lock:
            return list(self._skills.values())

    def remove(self, skill_id: str) -> None:
        """卸载技能；不存在抛 KeyError（对齐 lookup）。"""
        with self._lock:
            self._skills.pop(skill_id)
            domain = _domain(skill_id)
            if domain in self._domain_index:
                self._domain_index[domain] = [
                    sid for sid in self._domain_index[domain] if sid != skill_id
                ]
            self._persist()

    def check_preconditions(self, skill: Skill, ctx: dict[str, Any]) -> bool:
        """前置条件不满足返回 False（PRECONDITION_FAILED）。"""
        return all(bool(ctx.get(p)) for p in skill.preconditions)

    def activate(self, skill_id: str, *, effect_tracker: EffectTracker | None = None) -> Skill:
        """显式启用：把 ``draft`` 技能迁至 ``active``（skills spec「技能启用」）。

        下载 / 注册所得的草稿技能只有经此显式动作才进路由（路由放行集仍只含 ``active`` /
        ``gray``，见 ``router``）。已 ``active`` 时**幂等**返回、不重复落盘与登记效应；
        未知 id 抛 ``KeyError``（对齐 ``lookup`` / ``remove``，不静默创建）。注入
        ``effect_tracker`` 时登记可逆效应（undo 恢复启用前状态），未注入不记（零行为变化）。
        """
        with self._lock:
            skill = self._skills[skill_id]
            if skill.status == "active":
                return skill
            previous = skill.status
            skill.status = "active"
            self._persist()
            self._track_activation(skill_id, previous, effect_tracker)
            return skill

    def deprecate(self, skill_id: str, *, effect_tracker: EffectTracker | None = None) -> Skill:
        """退役：把技能迁至 ``deprecated``（skills spec「SOP 技能退役」）。

        已 ``deprecated`` 时**幂等**返回、不重复落盘与登记效应；未知 id 抛 ``KeyError``
        （对齐 ``lookup`` / ``remove``）。注入 ``effect_tracker`` 时登记可逆效应（undo 恢复
        退役前状态），未注入不记（零行为变化）。退役技能自动退出路由（放行集只含
        ``active`` / ``gray``），**不**物理删除、可经 ``activate`` 显式复活。
        """
        with self._lock:
            skill = self._skills[skill_id]
            if skill.status == "deprecated":
                return skill
            previous = skill.status
            skill.status = "deprecated"
            self._persist()
            self._track_deprecation(skill_id, previous, effect_tracker)
            return skill

    # ---- 落盘 ----

    def _track_deprecation(
        self, skill_id: str, previous: str, tracker: EffectTracker | None
    ) -> None:
        """登记退役效应（未注入 tracker 时不记，缺省降级）。"""
        if tracker is None:
            return
        tracker.record(
            Effect(
                op="skills.deprecate",
                target=skill_id,
                undo=lambda: self._restore_status(skill_id, previous),
                reversible=True,
                coeffect=[],
                trace_id=_DEPRECATE_TRACE,
                ts=time.time(),
            )
        )

    def _track_activation(
        self, skill_id: str, previous: str, tracker: EffectTracker | None
    ) -> None:
        """登记启用效应（未注入 tracker 时不记，缺省降级）。"""
        if tracker is None:
            return
        tracker.record(
            Effect(
                op="skills.activate",
                target=skill_id,
                undo=lambda: self._restore_status(skill_id, previous),
                reversible=True,
                coeffect=[],
                trace_id=_ACTIVATE_TRACE,
                ts=time.time(),
            )
        )

    def _restore_status(self, skill_id: str, status: str) -> None:
        """回滚启用：恢复启用前状态；技能已不在库中则不动（幂等）。"""
        with self._lock, contextlib.suppress(KeyError):
            self._skills[skill_id].status = status
            self._persist()

    def _index(self, skill: Skill) -> None:
        """登记领域索引（注册与恢复共用，不落盘）。"""
        self._domain_index.setdefault(_domain(skill.skill_id), []).append(skill.skill_id)

    def _load(self) -> None:
        """恢复落盘技能；缺失 / 损坏 / 结构不符 → 空态（不抛，见 ``persist``）。"""
        raw = read_state(self._path)
        try:
            skills = [Skill(**item) for item in raw]
        except (TypeError, ValueError):
            return
        for skill in skills:
            self._skills[skill.skill_id] = skill
            self._index(skill)

    def _persist(self) -> None:
        write_state(self._path, [asdict(skill) for skill in self._skills.values()])
