"""配置数据模型。

对应接口：doc/03-interfaces/configuration-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    """LLM 配置（必选）。"""

    provider: str
    model: str
    endpoint: str
    api_key_ref: str  # api_key 的 ${VAR} 引用（非明文）


@dataclass(frozen=True)
class IMConfig:
    """IM 接入配置（可选）。"""

    gateway: str
    corp_id: str
    secret_ref: str  # secret 的 ${VAR} 引用（非明文）


@dataclass(frozen=True)
class AppConfig:
    """配置聚合：单一收口解析后的有效配置。"""

    llm: LLMConfig
    features: dict[str, bool] = field(default_factory=dict[str, bool])
    im: IMConfig | None = None
    extra: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class ValidationResult:
    """schema 校验结果。"""

    ok: bool
    errors: list[str] = field(default_factory=list[str])
