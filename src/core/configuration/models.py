"""配置数据模型。

对应接口：doc/03-interfaces/configuration-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .embedding_models import default_embedding_model


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
    reasoning_effort: str | None = None  # 推理档位 low/medium/high（可选）
    embedding_model: str = ""  # 用户显式 embedding 模型（空=未声明，见 effective_embedding_model）
    embedding_auto: bool = True  # 未显式声明时是否按端点推导默认 embedding 模型（change 0271）
    embedding_required: bool = False  # 有效 embedding 模型为空时是否阻断启动（change 0289）
    context_window: int = 0  # 模型上下文窗口（可选；0=未配置，不派生预算 —— 见 loop 预算控制）
    show_thinking: bool = False  # 思考回显开关（可选；缺省关 ⇒ 事件面零新增，见 loop / ui）
    timeout: float = 60.0  # 单次调用超时上限（秒，可选；缺省=实现类缺省，见 llm-provider）
    max_retries: int = 3  # 调用失败最大重试次数（可选；缺省=实现类缺省）

    @property
    def effective_embedding_model(self) -> str:
        """生效的 embedding 模型：显式值优先，否则按端点推导（开关可关）；均无 ⇒ 空。

        推导只影响**有效配置**，不回写 ``embedding_model`` 字段 —— 热更新基线与用户
        显式值语义保持不变（change 0271）。
        """
        if self.embedding_model:
            return self.embedding_model
        if not self.embedding_auto:
            return ""
        return default_embedding_model(self.endpoint)


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
    """schema 校验结果：``errors`` 阻断生效；``warnings`` 仅提示（不阻断）。"""

    ok: bool
    errors: list[str] = field(default_factory=list[str])
    warnings: list[str] = field(default_factory=list[str])
