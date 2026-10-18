"""已知模型输出能力表（change 0293 / ADR-0283 / 台账 E229）。

`model_windows.py` 回答「上下文窗口多大」，本模块回答「输出上限字段与上限值」：

- 上限字段：OpenAI 旧 chat 用 ``max_tokens``；o 系 / GPT-5 系要求 ``max_completion_tokens``；
- 最大输出：部分模型显著低于 ``loop.output_reserve`` 缺省值（如 ``gpt-4-turbo`` 为 4096），
  无条件下发 8192 会被端点以 400 拒绝；
- ``reasoning_effort`` 支持性：仅作**配置期告警**依据，运行期仍照常下发显式配置。

纪律（同 ADR-0175 的窗口表）：

- 只收录**有据可查**的常见模型族；未收录 ⇒ ``None``（「不知道」的诚实表达）；
- ``max_output_tokens = 0`` 与 ``supports_reasoning_effort = None`` 均表示**该项未知**，
  不钳制、不告警；
- 纯常量 + 纯函数；**不引入配置键**（无 CLI / env / yaml 面，不是第二真源）；
- 显式 ``loop.output_reserve`` 仍是首选上限，本表只允许**向下**收紧。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapability:
    """单个模型族的输出面能力。"""

    max_output_tokens: int  # 0 = 未知（不钳制）
    max_tokens_field: str = "max_tokens"
    supports_reasoning_effort: bool | None = None  # None = 未知（不告警）


# 有序「模型名子串 → 能力」表 —— **顺序即特异性**：更具体的前缀须排在更笼统的前缀之前，
# 首个命中胜出（同 model_windows）。数值取各厂商公开文档的模型输出上限；只收常见族。
_KNOWN_CAPABILITIES: tuple[tuple[str, ModelCapability], ...] = (
    ("gpt-5", ModelCapability(128_000, "max_completion_tokens", True)),
    ("o4-mini", ModelCapability(100_000, "max_completion_tokens", True)),
    ("o3", ModelCapability(100_000, "max_completion_tokens", True)),
    ("o1", ModelCapability(100_000, "max_completion_tokens", True)),
    ("gpt-4o", ModelCapability(16_384, "max_tokens", False)),
    ("gpt-4.1", ModelCapability(32_768, "max_tokens", False)),
    ("gpt-4-turbo", ModelCapability(4_096, "max_tokens", False)),
    ("gpt-3.5", ModelCapability(4_096, "max_tokens", False)),
    ("deepseek", ModelCapability(8_192, "max_tokens", False)),
    # GLM-5 系：实测接受 reasoning_effort（2026-10-19 冒烟），最大输出未收录 ⇒ 不钳制
    ("glm-5", ModelCapability(0, "max_tokens", True)),
)


def known_capability(model: str) -> ModelCapability | None:
    """按模型名**子串**查能力（大小写不敏感，忽略首尾空白）；未命中 ⇒ ``None``。"""
    name = model.strip().lower()
    if not name:
        return None
    for needle, capability in _KNOWN_CAPABILITIES:
        if needle in name:
            return capability
    return None


def effective_output_tokens(model: str, requested: int | None) -> int | None:
    """请求上限 → 生效上限：已知模型上限更低时**向下钳制**，否则原值。"""
    if requested is None:
        return None
    capability = known_capability(model)
    if capability is None or capability.max_output_tokens <= 0:
        return requested
    return min(requested, capability.max_output_tokens)


def max_tokens_field(model: str) -> str:
    """该模型要求的输出上限字段名；未收录 ⇒ 既有字段 ``max_tokens``。"""
    capability = known_capability(model)
    return capability.max_tokens_field if capability is not None else "max_tokens"
