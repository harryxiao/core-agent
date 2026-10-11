"""技能迭代闭环（skill iteration）。

执行反馈不达标（样本达下限 + 失败率达阈值）→ 注入的改写器重写 ``instructions`` 为新版本
（草稿存于本模块，**不写回技能本体**）→ 经 ``VersionManager`` 灰度发布 → 两版本样本齐备后
A/B 定夺：提升落地新版本，退化丢弃草稿（**技能本身不弃用**）。

- 改写走 DI 接缝（复用 ``SopWriter``：prompt → 文本）——skills 不 import 任何 LLM 抽象
  （照 ``sop.py`` / ``memory/summarize.py``，ADR-0048 同一依赖方向）。
- 灰度与 A/B **复用既有** ``VersionManager``（ADR-0048 决策 ⑥ 记的缺口：能力已存在、无调用者）；
  指标口径 = 各版本成功率（``SkillFeedback.success_rate``）。

对应接口：doc/03-interfaces/skills-interface.md §4
"""

from __future__ import annotations

import time

from core.plugin_registry import Effect, EffectTracker

from .feedback import SkillFeedback, SkillStats
from .library import SkillLibrary
from .models import ABResult, Skill
from .sop import SopWriter
from .version import VersionManager

# 迭代触发门：执行样本下限 + 失败率阈值
_ITERATE_MIN_SAMPLES = 3
_ITERATE_FAILURE_RATE = 0.5

# 草稿灰度比例（仅该比例的任务走新版本）
_GRAY_RATIO = 0.3

# 连续 A/B 退化达此数即自动退役技能（skills spec「SOP 技能退役」；一次提升归零）
RETIRE_AFTER_DEGRADATIONS = 3

# 落地效应按此 trace 登记（回滚即恢复原版本与原 instructions）
_ITERATE_TRACE = "skills.iterate"

_PROMPT_HEAD = (
    "你是技能迭代器。下面是某技能的现行标准作业步骤与最近的实际执行情况。"
    "请针对失败给出更稳健的改进版步骤：只输出编号步骤清单，不要复述原文、不要解释理由。"
    "要求：在现行步骤基础上做**最小必要修改**，仍然有效的步骤保留原文；"
    "不得缩窄技能的适用任务范围；新增的防护步骤要写明它防的是哪一类失败。"
)


def build_iterate_prompt(skill: Skill, stats: SkillStats) -> str:
    """把「现行步骤 + 执行统计」渲染为改写 prompt。"""
    task_types = "、".join(skill.task_types) or "（未声明）"
    return "\n".join(
        [
            _PROMPT_HEAD,
            "",
            f"技能：{skill.skill_id}（{skill.description}）",
            f"适用任务：{task_types}",
            f"执行情况：{stats.total} 次，失败 {stats.fail} 次（失败率 {stats.failure_rate:.0%}）",
            "",
            "现行步骤：",
            skill.instructions or "（空）",
        ]
    )


def _next_version(version: str) -> str:
    """当前版本号 +1（``v1`` → ``v2``）；非常规版本号退化为追加后缀。"""
    if version.startswith("v") and version[1:].isdigit():
        return f"v{int(version[1:]) + 1}"
    return f"{version}+1"


class SkillIterator:
    """技能迭代器：反馈不达标 → 草稿 + 灰度 → A/B 定夺。"""

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        library: SkillLibrary,
        feedback: SkillFeedback,
        *,
        writer: SopWriter | None = None,
        versions: VersionManager | None = None,
        threshold: float = _ITERATE_FAILURE_RATE,
        min_samples: int = _ITERATE_MIN_SAMPLES,
        ratio: float = _GRAY_RATIO,
        tracker: EffectTracker | None = None,
        retire_after: int | None = None,
    ) -> None:
        self._library = library
        self._feedback = feedback
        self._writer = writer
        self._versions = (
            versions
            if versions is not None
            else VersionManager(
                library, metrics=lambda skill_id, version: feedback.success_rate(skill_id, version)
            )
        )
        self._threshold = threshold
        self._min_samples = min_samples
        self._ratio = ratio
        self._tracker = tracker
        # 连续退化阈值（None = 关闭 = 缺省；见 skills spec「SOP 技能退役」）
        self._retire_after = retire_after
        # 各技能**连续** A/B 退化计数（一次提升即归零；进程内状态）
        self._degradations: dict[str, int] = {}
        # 草稿版本 → instructions（不写回技能本体，定夺后胜者才落地）
        self._drafts: dict[str, dict[str, str]] = {}

    def resolve(self, skill: Skill) -> tuple[str, str]:
        """本轮该技能要用的 ``(版本, instructions)``：版本由 ``VersionManager.select`` 决定。"""
        version = self._versions.select(skill.skill_id, {})
        drafted = self._drafts.get(skill.skill_id, {})
        return version, drafted.get(version, skill.instructions)

    def consider(self, skill: Skill) -> str | None:
        """反馈不达标 → 生成下一版草稿并灰度，返回草稿版本号；否则返回 None（不改任何状态）。"""
        if self._writer is None or self._min_samples <= 0:
            return None
        stats = self._feedback.stats(skill.skill_id)
        if stats.total < self._min_samples or stats.failure_rate < self._threshold:
            return None
        draft = _next_version(skill.version)
        text = self._writer(build_iterate_prompt(skill, stats))
        if not text.strip():
            return None  # 空改写不入草稿（不写半成品）
        drafts = self._drafts.setdefault(skill.skill_id, {})
        drafts[skill.version] = skill.instructions  # 保留当前版本文本供 A/B 期间分流
        drafts[draft] = text
        self._versions.promote(skill.skill_id, draft, self._ratio)
        return draft

    def decide(self, skill: Skill) -> ABResult | None:
        """两版本样本齐备 → A/B 定夺（胜者落地、败者丢弃草稿）；样本未齐返回 None。

        开启 `retire_after` 时另计**连续**退化（一次提升归零）：达阈即自动退役技能
        （skills spec「SOP 技能退役」）。关闭时退化只丢草稿、不碰 `status`（逐字不变）。
        """
        drafts = self._drafts.get(skill.skill_id, {})
        draft = _next_version(skill.version)
        if draft not in drafts:
            return None
        current = skill.version
        if not (self._sampled(skill.skill_id, current) and self._sampled(skill.skill_id, draft)):
            return None
        result = self._versions.ab_test(skill.skill_id, current, draft)
        if result.winner == draft:
            if self._retire_after is not None:
                self._degradations.pop(skill.skill_id, None)  # 提升 ⇒ 归零
            self._apply(skill, draft, drafts[draft])
        else:
            del drafts[draft]  # 单次退化：只丢草稿，技能本体不动
            self._count_degradation(skill)
        return result

    def _count_degradation(self, skill: Skill) -> None:
        """累计一次退化；达阈退役并清计数（关闭 `retire_after` 时不记）。"""
        if self._retire_after is None:
            return
        count = self._degradations.get(skill.skill_id, 0) + 1
        if count < self._retire_after:
            self._degradations[skill.skill_id] = count
            return
        self._library.deprecate(skill.skill_id, effect_tracker=self._tracker)
        self._degradations.pop(skill.skill_id, None)

    # ---- 内部辅助 ----

    def _sampled(self, skill_id: str, version: str) -> bool:
        return self._feedback.stats(skill_id, version=version).total >= self._min_samples

    def _apply(self, skill: Skill, version: str, instructions: str) -> None:
        """落地新版本；登记可逆效应（回滚恢复原版本与原 instructions）。"""
        previous = (skill.version, skill.instructions)
        skill.version = version
        skill.instructions = instructions
        if self._tracker is None:
            return
        self._tracker.record(
            Effect(
                op="skills.iterate",
                target=skill.skill_id,
                undo=lambda: self._restore(skill, applied=version, previous=previous),
                reversible=True,
                coeffect=[],
                trace_id=_ITERATE_TRACE,
                ts=time.time(),
            )
        )

    def _restore(self, skill: Skill, *, applied: str, previous: tuple[str, str]) -> None:
        """恢复落地前的版本与说明；已被后续迭代覆盖则不动（幂等）。"""
        if skill.version == applied:
            skill.version, skill.instructions = previous
