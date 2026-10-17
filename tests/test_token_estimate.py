"""CJK 感知 token 估计（change 0245 / ADR-0233）。

口径：CJK 字符按 ≈1 token/字符计，其余 4 字符 ≈1 token，空串/极短文本至少 1。
上下文预算与记忆读预算（含会话转录）SHALL 共用同一估计器（memory 不得 import context）。
"""

from __future__ import annotations

from core.context import budget as budget_module
from core.context import estimate_tokens
from core.tokens import estimate_tokens as shared_estimate


def test_cjk_counts_per_char() -> None:
    assert estimate_tokens("你好世界") == 4  # noqa: PLR2004 — 4 字 = 4 token
    assert estimate_tokens("中" * 100) == 100  # noqa: PLR2004 — 逐字计


def test_ascii_keeps_legacy_divisor() -> None:
    assert estimate_tokens("abcdefgh") == 2  # noqa: PLR2004 — 8 // 4
    assert estimate_tokens("abc") == 1, "极短文本仍至少 1 token"


def test_empty_text_still_one() -> None:
    assert estimate_tokens("") == 1


def test_mixed_text_sums_both_buckets() -> None:
    assert estimate_tokens("你好abcdefgh") == 4  # noqa: PLR2004 — 2 CJK + 8 // 4


def test_context_and_memory_share_one_estimator() -> None:
    """两个调用面共用 `core.tokens`，防止口径漂移。"""
    assert budget_module.estimate_tokens is shared_estimate
    assert estimate_tokens is shared_estimate
