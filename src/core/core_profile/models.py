"""核心画像数据模型。

对应接口：doc/03-interfaces/core-profile-interface.md §1 / §2 / §4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CoreProfile:
    """两级 Core.md 解析后的画像：三个分区内容 + 来源。"""

    constitution: list[str] = field(default_factory=list[str])  # → constitution:v1 coeffect
    personality: list[str] = field(default_factory=list[str])  # → L0 记忆层
    project_info: list[str] = field(default_factory=list[str])  # → ContextEngine 上下文
    source: str = ""  # "~/.core/Core.md" | "<project>/Core.md" | "merged"


@dataclass
class AssembledProfile:
    """运行时注入单元：宪法 coeffect + 人格 + 项目上下文。"""

    coeffect: dict[str, Any] = field(default_factory=dict[str, Any])  # {"constitution:v1": [...]}
    personality: list[str] = field(default_factory=list[str])
    context: list[str] = field(default_factory=list[str])


@dataclass
class Section:
    """一个语义分区：kind 标识分区类型，lines 承载内容行。"""

    kind: str  # "constitution" | "personality" | "project_info"
    lines: list[str] = field(default_factory=list[str])
