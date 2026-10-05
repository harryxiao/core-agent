"""宠物安全边界（pet-safety）：只读优先 + 不可逆禁止 + 爆炸半径可控。

`SafetyBounds` 是边界判定；`build_safety_middleware` 把它接到 loop 的 before 接缝（R12 执行点）。
"""

from .middleware import build_safety_middleware
from .safety import SafetyBounds

__all__ = ["SafetyBounds", "build_safety_middleware"]
