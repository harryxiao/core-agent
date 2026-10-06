"""技能路由（SkillRouter）。

按任务类型匹配最合适技能，返回匹配度排序的 Top-K；无匹配回退通用流程，
记录未命中（供后续新技能沉淀）。专属技能（`beast.<域>.<技能>`）按 domain 作用域过滤。
词法匹配是 fast path（零模型调用）；词法**全无命中**时经注入的语义打分器兜底（缺省不启用）。

对应接口：doc/03-interfaces/skills-interface.md §4
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.memory import MemoryEntry, MemoryStore

from .feedback import SkillFeedback
from .library import SkillLibrary
from .models import Skill, SkillMatch

# 语义打分器契约：(任务文本, 候选技能快照) → {skill_id: 分值}；缺省不启用（纯词法）。
# 快照为 dict（不含 skills 类型）——打分器实现（judgment 域）不必依赖本模块。
SkillScorer = Callable[[str, list[dict[str, Any]]], dict[str, float]]

# 语义分低于此值不采纳（否则任何任务都能挂上某条技能，技能块被灌水进 prompt）
_SEMANTIC_MIN_SCORE = 0.5

# 命中快照里 instructions 的字符上界（token 有界；与 _MAX_STEP_CHARS 同口径）
_MAX_HINT_CHARS = 400

# 专属技能 skill_id 的节数（`beast.<域>.<技能>`）——形状即约定（非另建注册表）
_DEDICATED_SEGMENTS = 3

# 历史成功率因子的下限（有样本时）：零成功仍保留一半排序分，避免「一次失败即永不入选」的
# 正反馈（失败 → 不入选 → 无新样本 → 永久失败）
_SUCCESS_FLOOR = 0.5


def skill_hint(skill_id: str, version: str, instructions: str) -> dict[str, str]:
    """命中技能的提示快照——loop 渲染用**纯数据**（不暴露 skills 类型）。"""
    return {
        "skill_id": skill_id,
        "version": version,
        "instructions": instructions[:_MAX_HINT_CHARS],
    }


class SkillRouter:
    """技能路由：任务 → 匹配度排序的 Top-K 技能。"""

    def __init__(
        self,
        library: SkillLibrary,
        *,
        memory: MemoryStore | None = None,
        scorer: SkillScorer | None = None,
        feedback: SkillFeedback | None = None,
        threshold: float = _SEMANTIC_MIN_SCORE,
    ) -> None:
        self._library = library
        self._memory = memory
        self._scorer = scorer
        self._feedback = feedback
        self._threshold = threshold
        self.misses: list[str] = []

    def match(
        self,
        task: str,
        *,
        domain: str | None = None,
        top_k: int = 3,
        session_id: str = "",
    ) -> list[SkillMatch]:
        """按任务类型匹配，返回匹配度排序的 Top-K；无匹配返回空列表并记录未命中。

        词法命中即返回（fast path，零模型调用）；词法全无命中时才走语义兜底，
        语义有命中即视为命中（不记未命中）。

        ``session_id`` 为调用方会话标识（缺省空串 = 未归属），决定未命中记录的归属。

        ``domain`` 是**专属技能作用域**（缺省 = 通用视角）：三节 ``beast.<域>.<技能>`` 形式的
        专属技能仅当 ``domain == "beast.<域>"`` 时进候选——主 Agent 不带 domain，故神兽神通
        不会灌进主 prompt（beast-mode spec「Innate Skills and Dedicated Routing」）。

        返回的 ``score`` 是**排序分** = 基础分 × 历史成功率因子（见 ``_rank``）；**命中判定**
        （词法 > 0、语义 ≥ 阈值）一律判基础分——加权不改「算不算命中」（skills spec「技能路由」）。
        """
        terms = terms_of(task)
        candidates = [
            s
            for s in self._library.all_skills()
            if s.status in ("active", "gray") and _dedicated_domain(s.skill_id) in (None, domain)
        ]
        scored = [SkillMatch(skill=s, score=self._score(s, terms)) for s in candidates]
        scored = [m for m in scored if m.score > 0] or self._semantic(task, candidates)
        # 判定已由基础分完成，此处只把排序分换成复合分（加权不改命中口径）
        scored = [SkillMatch(skill=m.skill, score=self._rank(m.skill, m.score)) for m in scored]
        scored.sort(key=lambda m: m.score, reverse=True)
        if not scored:
            self._record_miss(task, session_id)
        return scored[:top_k]

    # ---- 内部辅助 ----

    def _semantic(self, task: str, candidates: list[Skill]) -> list[SkillMatch]:
        """语义兜底：逐候选打分，取达阈值者（打分器缺省/故障/低于阈值即空，等价纯词法）。"""
        if self._scorer is None:
            return []
        try:
            scores = self._scorer(task, [_snapshot(skill) for skill in candidates])
        except Exception:  # noqa: BLE001 — 打分器故障降级为词法，不中断路由
            return []
        return [
            SkillMatch(skill=skill, score=value)
            for skill in candidates
            if (value := scores.get(skill.skill_id, 0.0)) >= self._threshold
        ]

    def _rank(self, skill: Skill, base: float) -> float:
        """排序分 = 基础分 × 历史成功率因子（`SkillMatch.score` 自述口径的「历史成功率」项）。

        因子：**无样本恒为 1.0**（冷启动中性——``success_rate`` 无样本返回 0.0，直接相乘会把
        全部新技能归零）；有样本时 ``下限 + (1 - 下限) × 成功率``（``skill.version`` 的统计，
        旧版本历史不计入）。未注入反馈记录器 → 恒 1.0（与纯基础分一致）。
        """
        if self._feedback is None:
            return base
        stats = self._feedback.stats(skill.skill_id, version=skill.version)
        if stats.total == 0:
            return base
        return base * (_SUCCESS_FLOOR + (1.0 - _SUCCESS_FLOOR) * (stats.ok / stats.total))

    def _score(self, skill: Skill, terms: list[str]) -> float:
        if not terms:
            return 0.0
        haystack = " ".join([skill.skill_id, skill.description, *skill.task_types]).lower()
        hits = sum(1 for t in terms if t in haystack)
        return hits / len(terms)

    def _record_miss(self, task: str, session_id: str = "") -> None:
        """记录未命中任务；条目按调用方会话归属（缺省空串 = 全局层）。

        id 带会话键（缺省 ``default``）⇒ 不同会话的未命中记录不互相覆盖；``session_id``
        非空的记录不再成为他会话可见的全局条目（技能沉淀仍按会话归组）。
        """
        self.misses.append(task)
        if self._memory is None:
            return
        key = session_id or "default"
        self._memory.write(
            "L2",
            MemoryEntry(
                id=f"skills.miss.{key}.{len(self.misses)}",
                layer="L2",
                content=f"路由未命中: {task}",
                tags=["skills", "miss"],
                source="skills",
                trace_id="skills",
                session_id=session_id,
            ),
        )


def _snapshot(skill: Skill) -> dict[str, Any]:
    """技能快照：供域外打分器消费的最小字段（不暴露 skills 类型）。"""
    return {
        "skill_id": skill.skill_id,
        "description": skill.description,
        "task_types": list(skill.task_types),
    }


def _dedicated_domain(skill_id: str) -> str | None:
    """专属技能（``beast.<域>.<技能>`` 三节）的归属域 ``beast.<域>``；通用技能返回 ``None``。

    以 skill_id **形状**判定（而非另建注册表）：与 ``Beast.agent_id = "beast.<拼音>"`` /
    ``innate_skill = "beast.<拼音>.<技能>"`` 天然对齐，路由期即可按域过滤。
    """
    parts = skill_id.split(".")
    if len(parts) == _DEDICATED_SEGMENTS and parts[0] == "beast":
        return f"{parts[0]}.{parts[1]}"
    return None


def terms_of(text: str) -> list[str]:
    """任务/技能声明的词元（小写空白切分）：路由打分与 SOP 归组共用同一口径。"""
    return [t for t in text.lower().split() if t]
