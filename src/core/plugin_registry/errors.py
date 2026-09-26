"""插件注册表领域错误（plugin-registry）。

以结构化错误码表达插件注册 / 卸载 / 依赖解析 / 效应回滚等场景的失败，
不向调用方抛裸异常：上层捕获 :class:`DomainError` 并按 ``code`` 分支处理。

业务异常与系统异常分层的约定见 ``doc/05-development/development-standards.md``
主题 7：本模块全部错误均属业务异常，统一继承 :class:`DomainError`。

对应接口：doc/03-interfaces/plugin-registry-interface.md §7
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """插件注册表结构化错误码。"""

    COEFFECT_MISSING = "COEFFECT_MISSING"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    INVALID_MANIFEST = "INVALID_MANIFEST"
    GENERATION_CONFLICT = "GENERATION_CONFLICT"
    NOT_ACTIVE = "NOT_ACTIVE"
    UNDO_FAILED = "UNDO_FAILED"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    REGISTER_TIMEOUT = "REGISTER_TIMEOUT"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    INSTALL_FAILED = "INSTALL_FAILED"


class DomainError(Exception):
    """业务异常基类：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
