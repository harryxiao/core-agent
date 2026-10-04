"""embedding 批量适配器（memory）。

``MemoryStore.embedder`` 契约是**批量**可调用 ``(list[str]) -> list[list[float]]``；而
单条可调用（如 rag ``Embedder.embed(text) -> list[float]``）与之不匹配。本适配器把单条
可调用桥接为批量契约——memory **不 import rag**（L2 不依赖 rag 抽象），依赖方向由 L5
组合根在装配时注入。

对应接口：doc/03-interfaces/memory-interface.md §3
"""

from __future__ import annotations

from collections.abc import Callable


def batch_embed(
    single: Callable[[str], list[float]],
) -> Callable[[list[str]], list[list[float]]]:
    """把「单条文本 → 向量」适配为 ``MemoryStore`` 的批量契约。"""

    def _batch(texts: list[str]) -> list[list[float]]:
        return [single(text) for text in texts]

    return _batch
