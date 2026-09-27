"""组合与分发层领域错误码（composition）。

结构化错误码与异常分离：bundle 校验失败 / 循环依赖 / patch 覆盖冲突 / 插件缺失，
以领域异常承载，不向模型抛裸异常。

对应接口：doc/03-interfaces/composition-interface.md §错误码
"""

from __future__ import annotations

from enum import StrEnum


class CompositionErrorCode(StrEnum):
    """组合与分发层结构化错误码。"""

    BUNDLE_INVALID = "BUNDLE_INVALID"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    PATCH_CONFLICT = "PATCH_CONFLICT"
    PLUGIN_MISSING = "PLUGIN_MISSING"


class CompositionError(Exception):
    """组合与分发层业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: CompositionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
