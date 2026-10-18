"""CJK 感知 token 估计（change 0245 / ADR-0233；提速 change 0276 / ADR-0266）。

口径：CJK 字符按 ≈1 token/字符计，其余 4 字符 ≈1 token，空串/极短文本至少 1。
上下文预算与记忆读预算（含会话转录）SHALL 共用同一估计器（memory 不得 import context）。
`0276` 把逐字符区间判定改为预编译正则计数 —— 输出口径 SHALL 逐位不变（区间边界测试守护）。
"""

from __future__ import annotations

from core.context import budget as budget_module
from core.context import estimate_tokens
from core.tokens import estimate_tokens as shared_estimate

# CJK 区间表（与 `core.tokens` 契约同源，刻意在测试侧独立复写：实现侧改区间须显式同步本表）。
_CJK_RANGES = (
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xAC00, 0xD7AF),
    (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
)


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


def _reference(text: str) -> int:
    """逐字符参考实现（`0276` 之前的判定方式），用于钉住正则化后的口径。"""
    cjk = sum(1 for char in text if any(low <= ord(char) <= high for low, high in _CJK_RANGES))
    return max(1, cjk + (len(text) - cjk) // 4)


def test_cjk_range_boundaries_match_reference() -> None:
    """每个 CJK 区间的下界/上界/界外 ±1 与混合串均与逐字符判定逐位一致。"""
    samples = [""]
    samples.extend(
        chr(code)
        for low, high in _CJK_RANGES
        for code in (low - 1, low, low + 1, high - 1, high, high + 1)
    )
    samples.extend(
        [
            "a",
            "1",
            " ",
            "\n",
            "中a中",
            "你好abc世界",
            "".join(chr(low) for low, _ in _CJK_RANGES),
        ]
    )
    for sample in samples:
        assert shared_estimate(sample) == _reference(sample), repr(sample)
