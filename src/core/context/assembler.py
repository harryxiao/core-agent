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

# 单文档注入的指针上界（目录层须**薄**：全文不进窗口，见 context spec「信息地图」）
_MAX_POINTERS_PER_DOC = 8


def _matches_any(value: str, prefixes: tuple[str, ...]) -> bool:
    """``value`` 是否以 ``prefixes`` 中任一前缀开头（**前缀**语义，非子串）。"""
    return any(value.startswith(prefix) for prefix in prefixes)


class DynamicAssembler:
    """上下文装配器：按需加载 + 预算控制 + 地图取详情。"""

    def __init__(  # noqa: PLR0913 — 装配级配置项（含排除面/例外面）本就多维
        self,
        *,
        memory: MemoryStore | None = None,
        info_map: InfoMap | None = None,
        constitution: list[str] | None = None,
        project_info: list[str] | None = None,
        exclude_source_prefixes: tuple[str, ...] = (),
        allow_source_prefixes: tuple[str, ...] = (),
        # 事实面排除面（change 0185 / ADR-0176）：按 `MemoryEntry.source` **前缀**把条目挡在
        # 「相关事实」注入面之外 —— 用于**已由专块注入**的压缩产物（会话长期/中期摘要，
        # `source="compaction"`），避免同一份正文经两条通道重复注入。缺省空 ⇒ 不建过滤、
        # 装配结果与既往**逐字一致**；与 `exclude_source_prefixes`（**封存**面）
        # **不同理由、不合并**。
        exclude_fact_sources: tuple[str, ...] = (),
    ) -> None:
        self._memory = memory
        self._info_map = info_map if info_map is not None else InfoMap()
        self._constitution = list(constitution or [])
        self._project_info = list(project_info or [])
        self._exclude_source_prefixes = tuple(exclude_source_prefixes)
        self._allow_source_prefixes = tuple(allow_source_prefixes)
        self._exclude_fact_sources = tuple(exclude_fact_sources)

    def with_allow_source_prefixes(self, *prefixes: str) -> DynamicAssembler:
        """派生装配器：**排除面逐字继承**，放行面替换为给定前缀（排除面的例外面）。

        神兽用例：主 Agent 侧的封存（排除 `beast.*`）不变，放行**自身** `beast.<agent_id>`
        ⇒ 兽可召回自己的过往经验，他兽仍被排除（beast-mode spec「Independent Sub-Agent」）。
        派生而非原地改：主 loop 与神兽共用一份配置，原地改会波及主 loop（封存红线）。
        """
        return DynamicAssembler(
            memory=self._memory,
            info_map=self._info_map,
            constitution=list(self._constitution),
            project_info=list(self._project_info),
            exclude_source_prefixes=self._exclude_source_prefixes,
            allow_source_prefixes=tuple(prefixes),
            exclude_fact_sources=self._exclude_fact_sources,
        )

    def build(self, task: str, stage: str, *, budget: int, session_id: str = "") -> ContextPack:
        """按任务装配上下文：宪法 + 项目信息必保，事实按任务检索（query=task），超预算裁剪。

        ``session_id`` 为调用方会话标识（缺省空串 = 未归属），透传至 L2 事实检索的会话维度。
        读**信息地图**注入目录层 ``pointers``（仅指针，全文不进窗口）——地图为空 ⇒ 逐字不变。
        """
        project = [{"source": "project", "content": line} for line in self._project_info]
        pack = ContextPack(
            task=task,
            stage=stage,
            facts=project + self._gather_facts(task, budget, session_id),
            constitution=list(self._constitution),
            pending=[],
            pointers=self._gather_pointers(task),
        )
        return BudgetManager().enforce(pack, budget)

    def fetch_detail(self, pointer: str) -> str:
        """按信息地图指针跳转取细节（``doc_id#section``）——模型按需取详情的消费面。

        见 context spec「地图定位与按需取详情」：先用地图定位指针，再 fetch 对应片段，
        **而非加载全文**。指针无命中 ⇒ 空串（不抛，任务不因指针失效中断）。
        """
        doc_id, _, section = pointer.partition("#")
        pointers = self._info_map.lookup(doc_id, section or doc_id)
        if not pointers:
            return ""
        return pointers[0].summary

    # ---- 内部辅助 ----

    def _gather_pointers(self, task: str) -> list[dict[str, str]]:
        """读信息地图：把各已登记文档的**任务匹配指针**汇成目录层（每文档上界见常量）。

        未建索引的文档由 ``InfoMap.lookup`` 走受控线性扫描兜底 ⇒ 索引不可用亦逐段命中
        （context spec「重建失败二阶兜底」）。
        """
        out: list[dict[str, str]] = []
        for doc_id in self._info_map.documents():
            out.extend(
                {
                    "doc_id": pointer.doc_id,
                    "section": pointer.section,
                    "summary": pointer.summary,
                    "pointer": f"{pointer.doc_id}#{pointer.section}",
                }
                for pointer in self._info_map.lookup(doc_id, task)[:_MAX_POINTERS_PER_DOC]
            )
        return out

    def _gather_facts(self, query: str, budget: int, session_id: str = "") -> list[dict[str, str]]:
        """以任务目标为检索 query 召回 L2 事实（stage 不参与检索，架构图 :117）。

        ``exclude_source_prefixes`` 为装配级配置（缺省空 ⇒ 不含排除）；``session_id`` 为调用方
        会话标识（缺省空串 ⇒ 不过滤）。两者皆缺省时调用形态与既往逐字一致。

        ``exclude_fact_sources``（change `0185` / ADR-0176）为**事实面排除面**：命中 `e.source`
        前缀的条目被挡在注入**步骤**（读**后**过滤）—— 与 `exclude_source_prefixes` 的分工：
        后者是**封存**面（先于排名/预算过滤，语义是「该命名空间对本 agent 永不可见」），
        本参数是**去重**面（「已由专块注入，故不重复」）。缺省空 ⇒ **不建过滤**、返回路径与既往
        **逐字相同**。代价：被挡条目已吃掉事实面预算 —— 有界（每会话长期/中期各一条），
        见 ADR-0176 局限①。
        """
        if self._memory is None:
            return []
        if self._exclude_source_prefixes or session_id:
            entries = self._memory.read(
                query,
                budget,
                exclude_source_prefixes=self._exclude_source_prefixes,
                allow_source_prefixes=self._allow_source_prefixes,
                session_id=session_id,
            )
        else:
            entries = self._memory.read(query, budget)  # 未启用排除 ⇒ 调用形态与既往逐字一致
        if self._exclude_fact_sources:
            entries = [e for e in entries if not _matches_any(e.source, self._exclude_fact_sources)]
        return [{"source": e.source, "content": e.content} for e in entries]
