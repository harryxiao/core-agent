"""配置数据模型。

对应接口：doc/03-interfaces/configuration-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConfigExposure(StrEnum):
    """配置项暴露面分级。"""

    CORE = "core"
    ADVANCED = "advanced"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class ConfigSpec:
    """配置项单一真源：cli_flag / env_var / default / map_to / 暴露面。"""

    key: str  # 点分配置键，如 "llm.model"
    cli_flag: str  # "--llm.model"
    env_var: str  # "CORE_LLM_MODEL"
    default: Any = None
    map_to: str = ""  # yaml 目标路径（点分），如 "llm.model"
    exposure: ConfigExposure = ConfigExposure.CORE


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
class PetConfig:
    """宠物模式配置（可选）。"""

    enabled: bool = False
    persons_dir: str = "persons"


@dataclass(frozen=True)
class JudgmentConfig:
    """决策模型配置（可选）：未配置 provider 时决策能力关闭、回退主 LLM。"""

    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key_ref: str = ""  # api_key 的 ${VAR} 引用（非明文）
    confidence_threshold: float = 0.7


@dataclass(frozen=True)
class AppConfig:
    """配置聚合：单一收口解析后的有效配置。"""

    llm: LLMConfig
    features: dict[str, bool] = field(default_factory=dict[str, bool])
    im: IMConfig | None = None
    pet: PetConfig | None = None
    judgment: JudgmentConfig | None = None
    extra: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class ValidationResult:
    """schema 校验结果。"""

    ok: bool
    errors: list[str] = field(default_factory=list[str])
