"""Coeffect 共效应解析（CoeffectResolver）。

插件显式声明 ``coeffects``（执行前需注入的环境约束：权限 / 宪章 / 配置），
本解析器在调用前解析注入，缺失则拒绝执行（``COEFFECT_MISSING``）。
密钥类 coeffect 只注入句柄（``SecretRef``），原始值仅经 ``resolve_secret``
显式取出，绝不进日志 / 记忆（ADR-0003）。

对应接口：doc/03-interfaces/plugin-registry-interface.md §5
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from .errors import DomainError, ErrorCode


@dataclass(frozen=True)
class SecretRef:
    """密钥句柄：只引用不读取，repr 永远不暴露原始值。"""

    name: str

    def __repr__(self) -> str:
        return f"<secret:{self.name}>"


@dataclass(frozen=True)
class ResolvedContext:
    """解析注入后的 coeffect 结果集。"""

    values: dict[str, Any] = field(default_factory=dict[str, Any])

    def __contains__(self, key: str) -> bool:
        return key in self.values

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


class CoeffectMissing(DomainError):  # noqa: N818 — 接口契约命名（§5：抛 CoeffectMissing）
    """必需 coeffect 缺失时抛出。"""

    def __init__(self, required: list[str]) -> None:
        self.required = required
        super().__init__(ErrorCode.COEFFECT_MISSING, f"缺少必需 coeffect: {required}")


class CoeffectResolver:
    """从环境（配置 / 宪章 / 权限表）读取并注入 coeffect。"""

    def __init__(self) -> None:
        self._sources: dict[str, Any] = {}
        self._secret_values: dict[str, Any] = {}
        self._secrets: set[str] = set()
        self._lock = threading.RLock()

    def register(self, key: str, value: Any, *, secret: bool = False) -> None:
        """注册 coeffect 来源；``secret=True`` 时只注入句柄，原始值仅存私区。"""
        with self._lock:
            if secret:
                self._secrets.add(key)
                self._secret_values[key] = value
                self._sources[key] = SecretRef(key)
            else:
                self._sources[key] = value

    def resolve(self, required: list[str]) -> ResolvedContext:
        """解析注入 ``required`` 声明的 coeffect；缺失则抛 ``CoeffectMissing``。"""
        with self._lock:
            missing = [k for k in required if k not in self._sources]
        if missing:
            raise CoeffectMissing(missing)
        return ResolvedContext({k: self._sources[k] for k in required})

    def resolve_secret(self, key: str) -> Any:
        """显式取出密钥原始值（调用方在真正需要时使用，不落日志）。"""
        with self._lock:
            return self._secret_values[key]
