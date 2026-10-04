"""记忆接口协议骨架（L2 Memory）。

把 doc/03-interfaces/memory-interface.md 的接口契约提炼为
typing.Protocol 骨架：MemoryStore / Crystallizer / MemoryBackend，
只声明方法签名与 docstring，不含实现。

对应规格：doc/openspec/specs/memory/spec.md
模块设计：doc/02-modules/memory.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

Layer = Literal["L0", "L1", "L2", "L3", "L4"]
MemoryId = str


@dataclass
class MemoryEntry:
    """一条记忆条目。"""

    id: str
    layer: Layer
    content: str
    tags: list[str]
    source: str  # 来源（loop/evolution/user）
    trace_id: str
    reuse_count: int = 0  # 复用次数（结晶阈值依据）
    ts: float = 0.0  # 时间戳（接口文档无默认值，骨架补 0.0 以便 dataclass 构造）
    session_id: str = ""  # 会话 ID（跨轮记忆归组，缺省空串）


@dataclass
class IndexEntry:
    """L1 最小索引：条目 ID → 所属层。"""

    entries: list[tuple[str, Layer]]


class MemoryStore(Protocol):
    """记忆存储接口（可插拔后端，MVP 为 FileBackend）。"""

    plugin_id: str = "memory.store"

    def read(self, query: str, budget: int = 4096) -> list[MemoryEntry]:
        """检索相关记忆，返回按相关性排序的条目，总 token ≤ budget。"""
        ...

    def write(self, layer: Layer, entry: MemoryEntry) -> MemoryId:
        """写入记忆（带 trace_id / 来源 / 时间戳）。"""
        ...

    def migrate(self, entry_id: MemoryId, src: Layer, dst: Layer) -> None:
        """层间迁移：结晶(→代码层) / 溶解(→技能层)。"""
        ...

    def index(self) -> IndexEntry:
        """返回 L1 最小索引（IndexEntry）。"""
        ...

    def audit(self, trace_id: str | None = None) -> list[MemoryEntry]:
        """审计写入记录。"""
        ...


class Crystallizer(Protocol):
    """结晶 / 溶解钩子（联动 L4 Evolution Engine）。"""

    def crystallize(self, skill_entry: MemoryEntry) -> Any:
        """把 L3 技能提升为插件候选（PluginCandidate，交 L4 Validator）。"""
        ...

    def dissolve(self, plugin_id: str) -> MemoryEntry:
        """把失败插件降级为 L3 技能（保留教训）。"""
        ...


class MemoryBackend(Protocol):
    """记忆后端存储接口（可插拔，MVP 实现 FileBackend）。"""

    def get(self, layer: Layer, entry_id: MemoryId) -> MemoryEntry | None: ...

    def put(self, entry: MemoryEntry) -> MemoryId: ...

    def search(self, query: str, layer: Layer | None = None) -> list[MemoryEntry]: ...

    def list_index(self) -> IndexEntry: ...

    def delete(self, entry_id: MemoryId) -> None: ...
