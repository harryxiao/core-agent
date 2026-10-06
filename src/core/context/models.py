"""上下文工程数据模型。

对应接口：doc/03-interfaces/context-interface.md §1 / §3 / §4
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Pointer:
    """信息地图指针：定位长文档中的一个章节/要点。"""

    doc_id: str
    section: str
    summary: str
    offset: int | None = None


@dataclass
class MapEntry:
    """一份文档的信息地图：目录索引 + 内容指纹。"""

    doc_id: str
    content_hash: str
    pointers: list[Pointer] = field(default_factory=list[Pointer])


@dataclass
class ContextPack:
    """动态装配的上下文包（token 有硬上界）。

    ``pointers`` 为信息地图的**目录层**（章节指针，非全文）：装配器读信息地图后注入，
    模型据此按需 fetch 片段（context spec「信息地图」/「地图定位与按需取详情」）。
    缺省空 ⇒ 未接入信息地图时装配行为逐字不变。
    """

    task: str
    stage: str
    facts: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    constitution: list[str] = field(default_factory=list[str])
    pending: list[str] = field(default_factory=list[str])
    pointers: list[dict[str, str]] = field(default_factory=list[dict[str, str]])
    token_used: int = 0
    token_budget: int = 0


@dataclass
class Compaction:
    """多轮压实产物：关键信息摘要 + 被清理冗余 + 出处。"""

    conclusions: list[str] = field(default_factory=list[str])
    decisions: list[str] = field(default_factory=list[str])
    open_items: list[str] = field(default_factory=list[str])
    dropped: list[str] = field(default_factory=list[str])
    source_ids: list[str] = field(default_factory=list[str])  # 贡献历史的原始 id（出处追溯）
