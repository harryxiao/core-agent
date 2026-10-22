"""结晶 / 溶解（memory）。

把 L3 技能提升为插件候选（交 L4 Validator）、把失败插件降级为 L3 技能
（保留教训），是「经验 → 技能 → 插件」结晶链的钩子。

对应接口：doc/03-interfaces/memory-interface.md §4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .protocol import MemoryEntry

# 结晶阈值：与 SDD「技能晋级至少 3 次成功或 1 次显式用户要求」同口径（change 0305）。
CRYSTALLIZE_MIN_REUSE = 3


@dataclass
class PluginCandidate:
    """插件候选：由 L3 技能结晶而来，交 L4 Validator 验证。"""

    plugin_id: str
    generation: int
    schema: dict[str, Any]
    coeffects: list[str] = field(default_factory=list[str])
    source_entry_id: str = ""


class Crystallizer:
    """结晶 / 溶解钩子。"""

    def crystallize(
        self, skill_entry: MemoryEntry, *, force: bool = False
    ) -> PluginCandidate | None:
        """复用证据（或显式要求）达标才产出候选；未达标返回 ``None``。"""
        if not force and skill_entry.reuse_count < CRYSTALLIZE_MIN_REUSE:
            return None
        return PluginCandidate(
            plugin_id=f"skill.{skill_entry.id}",
            generation=1,
            schema={"type": "object", "content": skill_entry.content},
            source_entry_id=skill_entry.id,
        )

    def dissolve(self, plugin_id: str) -> MemoryEntry:
        return MemoryEntry(
            id=f"dissolved.{plugin_id}",
            layer="L3",
            content=f"失败插件 {plugin_id} 的教训（待复核）",
            tags=["dissolved", "lesson"],
            source="evolution",
            trace_id=f"evolution.dissolve.{plugin_id}",
        )
