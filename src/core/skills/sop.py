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
import warnings
from collections.abc import Callable, Sequence
from hashlib import blake2b
from pathlib import Path

from core.memory import redact_secrets
from core.persistence import read_state, write_state
from core.plugin_registry import Effect, EffectTracker

from .library import SkillLibrary
from .models import Skill
from .router import terms_of

# 提炼器契约：prompt → SOP 文本（同 ``memory.Summarizer`` 的「prompt → 文本」方向）
SopWriter = Callable[[str], str]

# 质量门契约：(任务文本, 提炼正文) → 是否放行（0198；由 judgment 侧 noul 提供实现，
# skills **不** import judgment，同 ``SopWriter`` 依赖方向）
SopGate = Callable[[str, str], bool]

# 同类任务累计多少条成功轨迹才提炼一次（提炼后清空该组，下批重新累积）
_SOP_MIN_SAMPLES = 3

# 单条轨迹入 prompt 的节选上界（token 有界）
_MAX_STEP_CHARS = 400

# 入库效应按此 trace 登记（回滚即移除本次提炼产物）
_EXTRACT_TRACE = "skills.extract"

_PROMPT_HEAD = (
    "你是 SOP 提炼器。下面是同一类任务的多次成功执行轨迹（任务 + 行动/结果序列）。"
    "请提炼为可复用的标准作业步骤：只输出编号步骤清单，不要复述轨迹、不要解释理由。"
    "要求：合并多次执行中重复出现的步骤，只保留每次执行都成立的必要步骤，剔除偶发细节；"
    "每步以动词开头，写清具体工具、路径、命令或参数，不要写「处理一下」这类空话；"
    "步骤数控制在 3-10 步。"
)


def build_sop_prompt(task: str, trajectories: Sequence[Sequence[str]]) -> str:
    """把一组成功轨迹渲染为提炼 prompt（**按轨迹分组**、逐条节选，token 有界）。

    分组是提炼质量的前提：拍平成一个长列表后，模型分辨不出哪几步属于同一次执行，
    也就识别不出「每次执行都出现」的公共步骤与偶发噪声。
    """
    blocks = [
        f"轨迹 {index}：\n" + "\n".join(f"- {step[:_MAX_STEP_CHARS]}" for step in steps)
        for index, steps in enumerate(trajectories, start=1)
    ]
    return "\n".join([_PROMPT_HEAD, "", f"任务：{task}", "", "成功轨迹：", *blocks])


def sop_writer_with(llm: Callable[[str], str]) -> SopWriter:
    """把「prompt → 文本」的模型调用适配为 ``SopExtractor`` 的提炼契约。"""

    def _write(prompt: str) -> str:
        return llm(prompt).strip()

    return _write


class SopExtractor:
    """SOP 提炼器：归组累积成功轨迹 → 达阈值提炼一条技能入库（可逆）。"""

    def __init__(  # noqa: PLR0913 — 构造注入面（提炼缝 + 裁定面 + 阈值 + 落盘 + 命名空间）
        self,
        library: SkillLibrary,
        *,
        writer: SopWriter | None = None,
        threshold: int = _SOP_MIN_SAMPLES,
        effect_tracker: EffectTracker | None = None,
        path: Path | None = None,
        namespace: str = "",
        gate: SopGate | None = None,
    ) -> None:
        self._library = library
        self._writer = writer
        self._threshold = threshold
        self._tracker = effect_tracker
        self._path = path
        # 发布前自动质量门（0198 / ADR-0188）：缺省 None ⇒ 发布路径**逐字不变**；
        # 由组合根以 judgment 的 noul 判定注入（skills 不知道 judgment 的存在）。
        self._gate = gate
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
        # 脱敏在空文本判定 / 质量门 / 入库**之前**（change 0254）：提炼器输出可能复述轨迹中的
        # 明文密钥；门看到的已是脱敏文本，入库正文不含明文。
        text = redact_secrets(self._writer(build_sop_prompt(task, group)))
        if not text.strip():
            return None  # 空提炼不入库（不写半成品），样本保留待下轮
        if self._gate is not None and not self._gate_ok(task, text):
            # 门未过 ⇒ 不发布 + **清组**（免同批样本反复触发提炼调用）+ 留痕**只报组键**。
            # 留痕绝不回显提炼正文（密钥红线）；未入库 ⇒ 无效应可回滚。
            warnings.warn(f"SOP 质量门未过，不入库（组键 {key}）", stacklevel=2)
            del self._samples[key]
            self._persist()
            return None
        skill = Skill(
            skill_id=_skill_id_for(key),
            description=f"SOP：{key}",
            task_types=[key],
            instructions=text,
            status="active",  # 维度1 技能库层：低风险自动发布（draft 对路由不可见）
        )
        if self._is_retired(skill.skill_id):
            # 粘性防复活（0205 / ADR-0195）：已退役的 id SHALL NOT 因重抽无声复活为 active
            # （复活须显式 `SkillLibrary.activate`）。清组免同批样本反复触发提炼调用；
            # 留痕**只报组键**，绝不回显提炼正文（密钥红线）。
            warnings.warn(f"SOP 技能已退役，重抽不复活（组键 {key}）", stacklevel=2)
            del self._samples[key]
            self._persist()
            return None
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

    def _gate_ok(self, task: str, text: str) -> bool:
        """过质量门；**判定故障 ⇒ 放行**（fail-open：门是注入的可调用，故障不阻断发布，
        也不中断主流程 —— 与规格「提炼失败 SHALL NOT 中断 Agent 主流程」同向）。"""
        gate = self._gate
        if gate is None:
            return True
        try:
            return bool(gate(task, text))
        except Exception:  # noqa: BLE001 — 门故障按放行
            return True

    def _is_retired(self, skill_id: str) -> bool:
        """该 id 是否已在库中且已退役（粘性防复活判据；不在库 ⇒ 未退役）。"""
        try:
            return self._library.lookup(skill_id).status == "deprecated"
        except KeyError:
            return False

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
