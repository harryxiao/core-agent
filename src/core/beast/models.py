"""神兽模式数据模型（beast-mode）。

会话状态（四态）/ 神兽定义（内置只读）两类数据结构。

对应接口：doc/03-interfaces/beast-mode-interface.md §1 / §2
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BeastSessionState(Enum):
    """神兽会话状态（四态：DORMANT → MANIFEST → ACTIVE → RECALLED）。"""

    DORMANT = "dormant"  # 未显形
    MANIFEST = "manifest"  # 已显形（召唤就位）
    ACTIVE = "active"  # 执行中
    RECALLED = "recalled"  # 已召回（记忆分区封存）


@dataclass(frozen=True)
class Beast:
    """内置神兽定义：唯一 id + 称号 + 领域职责 + 独有神通 + 能力标签。"""

    agent_id: str  # 全局唯一，如 "beast.qinglong"
    title: str  # 称号，如 "青龙"
    domain: str  # 领域 / 重大任务职责
    innate_skill: str  # 独有神通 skill_id，如 "beast.qinglong.blueprint"
    capabilities: tuple[str, ...] = ()  # 能力标签，供 MultiAgentRouter.match 打分
