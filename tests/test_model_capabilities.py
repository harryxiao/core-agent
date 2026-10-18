"""已知模型输出能力表（change 0293 / ADR-0283 / 台账 E229）。

验证「模型名子串 → 最大输出 / 上限字段 / reasoning_effort 支持性」的查表纪律：
只收录有据可查的族，未收录 / 未知能力不钳制、不告警。
"""

from __future__ import annotations

from core.configuration.model_capabilities import (
    effective_output_tokens,
    known_capability,
    max_tokens_field,
)


def test_known_capability_matches_families_case_insensitive() -> None:
    assert known_capability("gpt-4-turbo-2024-04-09").max_output_tokens == 4096  # noqa: PLR2004
    assert known_capability("GPT-4O").max_output_tokens == 16_384  # noqa: PLR2004
    assert known_capability("openai/gpt-5").max_tokens_field == "max_completion_tokens"
    assert known_capability("o1-preview").max_tokens_field == "max_completion_tokens"


def test_known_capability_prefers_specific_family() -> None:
    """更具体的族先命中：`gpt-4.1` 不应被更笼统的规则改写。"""
    assert known_capability("gpt-4.1-2025-04-14").max_output_tokens == 32_768  # noqa: PLR2004
    assert known_capability("gpt-4.1-2025-04-14").max_tokens_field == "max_tokens"


def test_unknown_capability_is_none() -> None:
    assert known_capability("my-local-model") is None
    assert known_capability("") is None


def test_effective_output_clamps_down_only() -> None:
    assert effective_output_tokens("gpt-4-turbo", 8192) == 4096  # noqa: PLR2004
    assert effective_output_tokens("gpt-4o", 8192) == 8192  # noqa: PLR2004 — 上限更高 ⇒ 不抬高
    assert effective_output_tokens("gpt-4o", 4096) == 4096  # noqa: PLR2004


def test_effective_output_unknown_keeps_requested() -> None:
    assert effective_output_tokens("my-local-model", 8192) == 8192  # noqa: PLR2004
    assert effective_output_tokens("glm-5.3", 8192) == 8192  # noqa: PLR2004 — 已知族但上限未知（0）
    assert effective_output_tokens("my-local-model", None) is None


def test_max_tokens_field_defaults_for_unknown() -> None:
    assert max_tokens_field("my-local-model") == "max_tokens"
    assert max_tokens_field("gpt-4o") == "max_tokens"
    assert max_tokens_field("o3-mini") == "max_completion_tokens"
