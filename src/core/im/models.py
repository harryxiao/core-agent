"""IM 网关数据模型（im）。

入站消息 / 会话隔离键。Message 可映射 distributed.Task（im=人→agent，
distributed=agent↔agent，边界不重叠，仅在互转处留注释，无硬依赖）。

对应接口：doc/03-interfaces/im-interface.md §2
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    """平台入站消息：platform/user_id/text/is_group + 会话隔离键。"""

    platform: str
    user_id: str
    text: str
    is_group: bool = False
    session_key: str = ""
    message_id: str = ""  # 消息唯一标识（幂等去重用，接口文档未列，轻微扩展）


@dataclass
class Session:
    """会话隔离：按 平台:用户/群 独立，多平台多用户互不串扰。"""

    session_key: str
    platform: str
    user_id: str
    history: list[str] = field(default_factory=list[str])
