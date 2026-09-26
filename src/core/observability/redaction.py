"""敏感信息脱敏（Redactor）。

遥测内容写入日志前必须脱敏：与 coeffect ``secret`` 标记联动——``SecretRef``
句柄只输出 ``<secret:name>``、已注册的明文密钥替换为 ``<redacted>``——并对
键名命中敏感词的值兜底脱敏，确保任何日志/遥测输出 grep 不到真实密钥。

对应规格：doc/openspec/specs/observability/spec.md（敏感信息脱敏）
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from core.plugin_registry import SecretRef

# 键名命中这些子串即视为敏感，值整体脱敏（兜底，与 coeffect 标记互补）
_SENSITIVE_KEY_PARTS = ("secret", "token", "password", "credential", "key")

_REDACTED = "<redacted>"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


class Redactor:
    """递归脱敏：SecretRef 句柄、注册明文、敏感键名三类来源。"""

    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def register_secret(self, value: str) -> None:
        """登记一条明文密钥；命中时替换为 ``<redacted>``。"""
        self._secrets.add(value)

    def redact(self, obj: Any) -> Any:
        if isinstance(obj, SecretRef):
            return repr(obj)  # "<secret:name>"，永不暴露原始值
        if isinstance(obj, str):
            return self._redact_text(obj)
        if isinstance(obj, Mapping):
            return self._redact_mapping(cast(Mapping[Any, Any], obj))
        if isinstance(obj, (list, tuple)):
            return [self.redact(item) for item in cast(list[Any], obj)]
        return obj

    def _redact_text(self, text: str) -> str:
        """把已登记密钥的整串或子串替换为 ``<redacted>``。"""
        result = text
        for secret in self._secrets:
            if secret and secret in result:
                result = result.replace(secret, _REDACTED)
        return result

    def _redact_mapping(self, obj: Mapping[Any, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in obj.items():
            k = str(key)
            out[k] = _REDACTED if _is_sensitive_key(k) else self.redact(value)
        return out
