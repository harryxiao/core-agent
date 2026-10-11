"""SOP 提炼（skill extraction）。

把**同一类任务的多次成功轨迹**聚合、提炼为一条 ``Skill``（``instructions`` 承载 SOP
步骤、``task_types`` 承载归组键）并经 ``SkillLibrary.register()`` 入库——这是技能库
「从经验到技能」的入口（此前只有注册/路由/版本三段，没有任何产生技能的路径）。

生成走 DI 接缝（``SopWriter``：prompt → 文本），**skills 不 import 任何 LLM / rag 抽象**
（照 ``memory/summarize.py`` 先例、ADR-0048 同一依赖方向），生产侧由 L5 组合根注入模型调用。

样本累积可落盘（注入 ``path``）：提交 / 清组即落盘、启动即恢复（样本跨进程续攒）；
缺省 ``path=None`` 纯内存（见 ``persist``）。

对应接口：doc/03-interfaces/skills-interface.md §6
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Sequence
from hashlib import blake2b
from pathlib import Path

from core.persistence import read_state, write_state
from core.plugin_registry import Effect, EffectTracker

from .library import SkillLibrary
from .models import Skill
from .router import terms_of

# 提炼器契约：prompt → SOP 文本（同 ``memory.Summarizer`` 的「prompt → 文本」方向）
SopWriter = Callable[[str], str]

# 同类任务累计多少条成功轨迹才提炼一次（提炼后清空该组，下批重新累积）
_SOP_MIN_SAMPLES = 3

# 单条轨迹入 prompt 的节选上界（token 有界）
_MAX_STEP_CHARS = 400

# 入库效应按此 trace 登记（回滚即移除本次提炼产物）
_EXTRACT_TRACE = "skills.extract"

_PROMPT_HEAD = (
    "你是 SOP 提炼器。下面是同一类任务的多次成功执行轨迹（任务 + 行动/结果序列）。"
    "请提炼为可复用的标准作业步骤：只输出编号步骤清单，不要复述轨迹、不要解释理由。"
)


def build_sop_prompt(task: str, steps: Sequence[str]) -> str:
    """把一组成功轨迹渲染为提炼 prompt（逐条节选，token 有界）。"""
    lines = [f"- {step[:_MAX_STEP_CHARS]}" for step in steps]
    return "\n".join([_PROMPT_HEAD, "", f"任务：{task}", "", "成功轨迹：", *lines])


def sop_writer_with(llm: Callable[[str], str]) -> SopWriter:
    """把「prompt → 文本」的模型调用适配为 ``SopExtractor`` 的提炼契约。"""

    def _write(prompt: str) -> str:
        return llm(prompt).strip()

    return _write


class SopExtractor:
    """SOP 提炼器：归组累积成功轨迹 → 达阈值提炼一条技能入库（可逆）。"""

    def __init__(  # noqa: PLR0913 — 构造注入面（提炼缝 + 阈值 + 落盘 + 命名空间）
        self,
        library: SkillLibrary,
        *,
        writer: SopWriter | None = None,
        threshold: int = _SOP_MIN_SAMPLES,
        effect_tracker: EffectTracker | None = None,
        path: Path | None = None,
        namespace: str = "",
    ) -> None:
        self._library = library
        self._writer = writer
        self._threshold = threshold
        self._tracker = effect_tracker
        self._path = path
        # 观察面命名空间（change 0197）：空 ⇒ 单轮面（逐字不变）；非空 ⇒ 组键**前缀化**，
        # 与单轮面样本隔离（不复用单轮 task_types、落不同 skill_id）。隔离是**正确性**要求 ——
        # 两步序语义不同（任务级 = 子任务骨架；单轮 = 工具调用行），混组会产出浑浊 SOP。
        self._namespace = namespace
        self._samples: dict[str, list[list[str]]] = {}
        self._load()

    def observe(self, task: str, steps: Sequence[str], *, ok: bool = True) -> Skill | None:
        """提交一条轨迹；达阈值则提炼入库并返回技能，否则返回 None。

        ``ok=False`` 的失败轨迹不是 SOP，直接丢弃（教训沉淀走 memory/evolution 通道）；
        未注入提炼器时不累积、不提炼（零额外模型调用）。
        """
        if not ok or self._writer is None or self._threshold <= 0:
            return None
        key = self._group_key(task)
        group = self._samples.setdefault(key, [])
        group.append(list(steps))
        self._persist()
        if len(group) < self._threshold:
            return None
        text = self._writer(build_sop_prompt(task, [step for traj in group for step in traj]))
        if not text.strip():
            return None  # 空提炼不入库（不写半成品），样本保留待下轮
        skill = Skill(
            skill_id=_skill_id_for(key),
            description=f"SOP：{key}",
            task_types=[key],
            instructions=text,
            status="active",  # 维度1 技能库层：低风险自动发布（draft 对路由不可见）
        )
        self._library.register(skill)
        self._track(skill)
        del self._samples[key]  # 提炼后清组，下批重新累积
        self._persist()
        return skill

    # ---- 落盘 ----

    def _load(self) -> None:
        """恢复落盘样本；缺失 / 损坏 / 结构不符 → 空态（不抛，见 ``persist``）。"""
        raw = read_state(self._path)
        try:
            self._samples = {
                str(key): [[str(chunk) for chunk in traj] for traj in trajs]
                for key, trajs in raw.items()
            }
        except (AttributeError, TypeError, ValueError):
            self._samples = {}

    def _persist(self) -> None:
        write_state(self._path, self._samples)

    # ---- 内部辅助 ----

    def _group_key(self, task: str) -> str:
        """归组键：优先复用词法命中的已有 ``task_types``，否则用任务词元签名。

        注入 ``namespace`` 时组键**前缀化**且词法复用**只在同命名空间内**进行（change 0197）：
        任务级观察面与单轮面完全隔离 —— 组键与 ``_skill_id_for`` 双双落**独立** id 空间，
        互不复用（否则单轮面会命中任务级键而把两类样本混组）。缺省空命名空间 ⇒ 键逐字不变。
        """
        terms = set(terms_of(task))
        if not terms:
            return self._apply_namespace(task.strip().lower())
        for skill in self._library.all_skills():
            for task_type in skill.task_types:
                if self._same_namespace(task_type) and terms & set(terms_of(task_type)):
                    return task_type  # 已是同命名空间键，直接复用
        return self._apply_namespace(" ".join(sorted(terms)))

    def _same_namespace(self, task_type: str) -> bool:
        """该 ``task_type`` 是否属本实例命名空间（空命名空间 ⇒ 只认无前缀键）。"""
        if self._namespace:
            return task_type.startswith(f"{self._namespace}::")
        return "::" not in task_type

    def _apply_namespace(self, key: str) -> str:
        return f"{self._namespace}::{key}" if self._namespace else key

    def _track(self, skill: Skill) -> None:
        """登记入库效应（未注入 tracker 时不记，缺省降级）。"""
        if self._tracker is None:
            return
        self._tracker.record(
            Effect(
                op="skills.register",
                target=skill.skill_id,
                undo=lambda: self._undo(skill),
                reversible=True,
                coeffect=[],
                trace_id=_EXTRACT_TRACE,
                ts=time.time(),
            )
        )

    def _undo(self, skill: Skill) -> None:
        """移除本次提炼产物；已被后续提炼覆盖则不动（幂等）。"""
        with contextlib.suppress(KeyError):
            if self._library.lookup(skill.skill_id) is skill:
                self._library.remove(skill.skill_id)


def _skill_id_for(key: str) -> str:
    """组键 → 确定性 skill_id（同组重复提炼覆盖同一条，不增长）。"""
    return f"skills.sop.{blake2b(key.encode('utf-8'), digest_size=8).hexdigest()}"
