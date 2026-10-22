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
MemoryStatus = Literal["active", "superseded"]
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
    ts: float = 0.0  # 时间戳
    session_id: str = ""  # 会话 ID（跨轮记忆归组，缺省空串）
    importance: float = 0.0  # 主观重要度 [0,1]（缺省 0 不调制；自动打分留 Phase 18 #4/#5）
    kind: Literal["episodic", "semantic"] = "episodic"  # 事件 / 提炼事实
    # 治理信封（change 0303）：旧行缺键 ⇒ 默认值加载；检索缺省只见 active。
    content_hash: str = ""  # 正文 strip() 后的 SHA-256（写入时自动计算）
    status: MemoryStatus = "active"
    version: int = 1  # 同链递增（关键事实版本链）
    parent_id: str = ""  # 被本版本替代的条目 id（首版空）
    superseded_by: str = ""  # 仅旧版本填写：替代它的新版本 id


@dataclass
class IndexEntry:
    """L1 最小索引：条目 ID → 所属层。"""

    entries: list[tuple[str, Layer]]


@dataclass
class RecallResult:
    """一次检索的结果与注入统计（change 0304 / ADR-0294）。

    不变式：``matched_count == injected_count + excluded_by_diversity + excluded_by_budget``。
    ``minimum_budget`` 为再注入第一条被预算跳过条目所需的最小预算（无预算剔除 ⇒ 0）。
    """

    entries: list[MemoryEntry]
    matched_count: int = 0
    injected_count: int = 0
    excluded_by_budget: int = 0
    excluded_by_diversity: int = 0
    minimum_budget: int = 0


class MemoryStore(Protocol):
    """记忆存储接口（可插拔后端，MVP 为 FileBackend）。"""

    plugin_id: str = "memory.store"

    def read(  # noqa: PLR0913 — 检索面扩展关键字（change 0301）
        self,
        query: str,
        budget: int = 4096,
        *,
        exclude_source_prefixes: tuple[str, ...] = (),
        allow_source_prefixes: tuple[str, ...] = (),
        session_id: str = "",
        include_forgotten: bool = False,
        layers: tuple[Layer, ...] = (),
    ) -> list[MemoryEntry]:
        """检索相关记忆，返回按相关性排序的条目，总 token ≤ budget。

        ``exclude_source_prefixes`` 命中的 ``source`` 前缀在排名前剔除（缺省空 ⇒ 语义不变）；
        ``allow_source_prefixes`` 是排除面的**例外面**（同时命中两者 ⇒ 放行）。
        ``session_id`` 非空 ⇒ 只返回本会话条目 + 全局层（缺省空串 ⇒ 不过滤）。
        ``include_forgotten`` 缺省 False ⇒ 带 ``forgotten`` 标签的条目在排名前剔除（change 0301）。
        ``layers`` 非空 ⇒ 只返回所列层，排名前剔除（缺省空 ⇒ 不施加层过滤；change 0302）。
        缺省只返回 ``status="active"`` 的条目（被取代版本仅在 ``audit()`` 可见；change 0303）。
        """
        ...

    def recall(  # noqa: PLR0913 — 与 read() 同参数
        self,
        query: str,
        budget: int = 4096,
        *,
        exclude_source_prefixes: tuple[str, ...] = (),
        allow_source_prefixes: tuple[str, ...] = (),
        session_id: str = "",
        include_forgotten: bool = False,
        layers: tuple[Layer, ...] = (),
    ) -> RecallResult:
        """检索相关记忆并返回注入统计（change 0304）；``read()`` == ``recall().entries``。

        检索管线在排名之后、预算之前施加多样性过滤（近重复抑制 + 每会话最多 3 条），
        被滤条目不吃预算、不被复用强化。
        """
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

    def compact(self, query: str = "", budget: int = 4096, *, deadline: float | None = None) -> Any:
        """压实记忆：会话摘要提炼（按 ``session_id`` 聚合）+ 重要性打分写回（可撤销）。

        ``deadline``（``time.monotonic`` 语义）为协作式截止：每次模型调用前检查，
        越界即停止后续调用；``None`` ⇒ 不设截止。
        """
        ...

    def summary_for(self, session_id: str) -> Any:
        """按会话取回既有摘要条目（只读；无则 ``None``）。"""
        ...

    def mid_summary_for(self, session_id: str) -> Any:
        """按会话取回既有**中层摘要**条目（只读；无则 ``None``）。"""
        ...

    def summarize_slice(
        self, session_id: str, entries: list[MemoryEntry], *, max_chars: int
    ) -> str | None:
        """把中带会话原文（prompt-only 桩）滚合并为中层摘要条目（不迁移来源，可撤销）。

        摘要器 UNWIRED / 无材料 / ``max_chars <= 0`` ⇒ ``None``、零写入。
        """
        ...

    def forget(self, *, threshold: float = 0.0) -> list[MemoryId]:
        """遗忘：衰减评分低于阈值的 L2 episodic 条目迁 L4 归档（可撤销，不物理删除）。"""
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
