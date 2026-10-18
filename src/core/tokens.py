"""粗略 token 估计（中性，change 0245 / ADR-0233；提速 change 0276 / ADR-0266）。

**CJK 字符按 ≈1 token/字符计，其余按 4 字符 ≈1 token**；空串/极短文本至少 1 token。
上下文预算（``context.budget``）与记忆读预算（``memory.store`` / ``memory.transcript``）共用
本模块 —— memory 不能 import context（ADR-0045），故估计器落在中性模块，口径只有一处。

粗估，不承诺与供应商 tokenizer 一致；CJK 取 1 token/字符是保守上界（宁高勿低：低估会让
预算事后失真，高估只是更早裁剪）。

对应接口：doc/03-interfaces/context-interface.md §5
"""

from __future__ import annotations

import re
from typing import Protocol

_DIVISOR = 4

# CJK 字符区间：统一表意文字（含扩展 A）、CJK 标点、假名、谚文、全角形式
_CJK_RANGES = (
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xAC00, 0xD7AF),
    (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
)


# 同一组区间编译为一个字符类：C 层 `sub` 计数替代逐字符 Python `any()` 判定。
# `0276` 只换计数方式，口径（哪些字符算 CJK）由 `_CJK_RANGES` 单处定义、逐位不变。
_CJK_PATTERN = re.compile(
    "[" + "".join(f"\\u{low:04x}-\\u{high:04x}" for low, high in _CJK_RANGES) + "]"
)


def estimate_tokens(text: str) -> int:
    """CJK 感知的粗略 token 估算（见模块 docstring）。"""
    cjk = len(text) - len(_CJK_PATTERN.sub("", text))
    return max(1, cjk + (len(text) - cjk) // _DIVISOR)


class TokenEstimator(Protocol):
    """token 估算器契约（change 0230 / G1）：可注入精确实现替换启发式。"""

    def estimate(self, text: str) -> int: ...


class HeuristicEstimator:
    """缺省估算器：委托共享启发式（CJK 感知，行为与引入注入点前逐字一致）。"""

    def estimate(self, text: str) -> int:
        return estimate_tokens(text)


DEFAULT_ESTIMATOR: TokenEstimator = HeuristicEstimator()
