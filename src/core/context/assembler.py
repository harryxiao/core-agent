"""动态上下文装配（DynamicAssembler）。

按任务阶段按需装配上下文：宪法分区必保注入、L2 事实按需检索、项目信息
未命中静默降级；超预算交 BudgetManager 裁剪。

对应接口：doc/03-interfaces/context-interface.md §2
"""

from __future__ import annotations

from core.memory import MemoryStore

from .budget import BudgetManager
from .info_map import InfoMap
from .models import ContextPack


class DynamicAssembler:
    """上下文装配器：按需加载 + 预算控制 + 地图取详情。"""

    def __init__(
        self,
        *,
        memory: MemoryStore | None = None,
        info_map: InfoMap | None = None,
        constitution: list[str] | None = None,
        project_info: list[str] | None = None,
    ) -> None:
        self._memory = memory
        self._info_map = info_map if info_map is not None else InfoMap()
        self._constitution = list(constitution or [])
        self._project_info = list(project_info or [])

    def build(self, task: str, stage: str, *, budget: int) -> ContextPack:
        """按阶段装配上下文：宪法 + 项目信息必保，事实按需检索，超预算裁剪。"""
        project = [{"source": "project", "content": line} for line in self._project_info]
        pack = ContextPack(
            task=task,
            stage=stage,
            facts=project + self._gather_facts(stage, budget),
            constitution=list(self._constitution),
            pending=[],
        )
        return BudgetManager().enforce(pack, budget)

    def fetch_detail(self, pointer: str) -> str:
        """按信息地图指针取片段详情（``doc_id#section``）。"""
        doc_id, _, section = pointer.partition("#")
        pointers = self._info_map.lookup(doc_id, section or doc_id)
        if not pointers:
            return ""
        return pointers[0].summary

    # ---- 内部辅助 ----

    def _gather_facts(self, stage: str, budget: int) -> list[dict[str, str]]:
        if self._memory is None:
            return []
        return [
            {"source": e.source, "content": e.content} for e in self._memory.read(stage, budget)
        ]
