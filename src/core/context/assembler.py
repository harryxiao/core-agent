"""动态上下文装配（DynamicAssembler）。

按任务按需装配上下文：宪法分区必保注入、L2 事实按任务检索、项目信息
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
        exclude_source_prefixes: tuple[str, ...] = (),
    ) -> None:
        self._memory = memory
        self._info_map = info_map if info_map is not None else InfoMap()
        self._constitution = list(constitution or [])
        self._project_info = list(project_info or [])
        self._exclude_source_prefixes = tuple(exclude_source_prefixes)

    def build(self, task: str, stage: str, *, budget: int, session_id: str = "") -> ContextPack:
        """按任务装配上下文：宪法 + 项目信息必保，事实按任务检索（query=task），超预算裁剪。

        ``session_id`` 为调用方会话标识（缺省空串 = 未归属），透传至 L2 事实检索的会话维度。
        """
        project = [{"source": "project", "content": line} for line in self._project_info]
        pack = ContextPack(
            task=task,
            stage=stage,
            facts=project + self._gather_facts(task, budget, session_id),
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

    def _gather_facts(self, query: str, budget: int, session_id: str = "") -> list[dict[str, str]]:
        """以任务目标为检索 query 召回 L2 事实（stage 不参与检索，架构图 :117）。

        ``exclude_source_prefixes`` 为装配级配置（缺省空 ⇒ 不含排除）；``session_id`` 为调用方
        会话标识（缺省空串 ⇒ 不过滤）。两者皆缺省时调用形态与既往逐字一致。
        """
        if self._memory is None:
            return []
        if self._exclude_source_prefixes or session_id:
            entries = self._memory.read(
                query,
                budget,
                exclude_source_prefixes=self._exclude_source_prefixes,
                session_id=session_id,
            )
        else:
            entries = self._memory.read(query, budget)  # 未启用排除 ⇒ 调用形态与既往逐字一致
        return [{"source": e.source, "content": e.content} for e in entries]
