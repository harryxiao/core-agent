"""宠物模式四层架构协议（pet-core）。

R7 四层解耦：基础属性层（PersonaLayer）/ 自主目标循环层（复用
core.loop.LoopPlugin）/ 探索工具集层（ExplorerLayer）/ 安全边界层
（SafetyLayer）。各层以 Protocol 声明，由 pet 子模块 library /
explore / safety 提供实现，独立配置与替换。

对应接口：doc/03-interfaces/pet-mode-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PersonaLayer(Protocol):
    """基础属性层：角色/性格/喜好/物种 + pet.md 人格 prompt。"""

    name: str
    species: str
    persona_text: str
    traits: list[str]
    preferences: list[str]

    def render_prompt(self) -> str: ...


class ExplorerLayer(Protocol):
    """探索工具集层：受限只读优先工具，清单可配置、需授权。"""

    def available(self) -> list[str]: ...

    def run(self, tool_id: str) -> str: ...


@dataclass
class SafetyDecision:
    """安全边界裁决：阻断与否 + 阻断原因。"""

    blocked: bool
    reason: str = ""


class SafetyLayer(Protocol):
    """安全边界层：只读优先、不可逆禁止、爆炸半径可控。"""

    def check(self, op: str, target: str) -> SafetyDecision: ...
