"""技能执行反馈（skill execution feedback）。

按 ``(skill_id, version)`` 累计「命中」与「成功/失败」，供技能迭代判定「反馈不达标」
（见 ``skills/iteration.py``）。缺省仅进程内统计（不写记忆）；注入 ``path`` 时落盘并在启动
恢复（见 ``persist``），不参与提示组装与终止语义。

对应接口：doc/03-interfaces/skills-interface.md §4
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .persist import read_state, write_state


@dataclass
class SkillStats:
    """单个 (技能, 版本) 的执行统计。"""

    hits: int = 0
    ok: int = 0
    fail: int = 0

    @property
    def total(self) -> int:
        """有结果的执行次数（命中但未收尾的不计入）。"""
        return self.ok + self.fail

    @property
    def failure_rate(self) -> float:
        """失败率（无样本 → 0.0）。"""
        return self.fail / self.total if self.total else 0.0


class SkillFeedback:
    """技能命中/结果记录器：累计到 (skill_id, version)。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._stats: dict[tuple[str, str], SkillStats] = {}
        self._load()

    def record_hit(self, skill_id: str, *, version: str) -> None:
        """技能进入 prompt 的那一轮记一次命中。"""
        self._of(skill_id, version).hits += 1
        self._persist()

    def record_outcome(self, skill_id: str, *, version: str, ok: bool) -> None:
        """一轮收尾的结果（成功/失败）记到该轮实际使用的版本上。"""
        stats = self._of(skill_id, version)
        if ok:
            stats.ok += 1
        else:
            stats.fail += 1
        self._persist()

    def stats(self, skill_id: str, *, version: str | None = None) -> SkillStats:
        """取某版本统计；``version=None`` 为各版本合计；无记录返回零值（不落空条目）。"""
        if version is not None:
            return self._stats.get((skill_id, version), SkillStats())
        matched = [s for (sid, _), s in self._stats.items() if sid == skill_id]
        return SkillStats(
            hits=sum(s.hits for s in matched),
            ok=sum(s.ok for s in matched),
            fail=sum(s.fail for s in matched),
        )

    def success_rate(self, skill_id: str, version: str) -> float:
        """某版本成功率（无样本 → 0.0）——技能 A/B 的指标口径（越高越好）。"""
        stats = self.stats(skill_id, version=version)
        return stats.ok / stats.total if stats.total else 0.0

    # ---- 落盘 ----

    def _load(self) -> None:
        """恢复落盘计数；缺失 / 损坏 / 结构不符 → 空态（不抛，见 ``persist``）。"""
        raw = read_state(self._path)
        try:
            restored = {
                (str(skill_id), str(version)): SkillStats(**stats)
                for skill_id, versions in raw.items()
                for version, stats in versions.items()
            }
        except (AttributeError, TypeError, ValueError):
            return
        self._stats.update(restored)

    def _persist(self) -> None:
        data: dict[str, dict[str, dict[str, int]]] = {}
        for (skill_id, version), stats in self._stats.items():
            data.setdefault(skill_id, {})[version] = asdict(stats)
        write_state(self._path, data)

    # ---- 内部辅助 ----

    def _of(self, skill_id: str, version: str) -> SkillStats:
        return self._stats.setdefault((skill_id, version), SkillStats())
