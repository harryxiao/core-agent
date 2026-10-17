"""粗略 token 估计（中性，change 0245 / ADR-0233）。

**CJK 字符按 ≈1 token/字符计，其余按 4 字符 ≈1 token**；空串/极短文本至少 1 token。
上下文预算（``context.budget``）与记忆读预算（``memory.store`` / ``memory.transcript``）共用
本模块 —— memory 不能 import context（ADR-0045），故估计器落在中性模块，口径只有一处。

粗估，不承诺与供应商 tokenizer 一致；CJK 取 1 token/字符是保守上界（宁高勿低：低估会让
预算事后失真，高估只是更早裁剪）。

对应接口：doc/03-interfaces/context-interface.md §5
"""

from __future__ import annotations

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


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _CJK_RANGES)


def estimate_tokens(text: str) -> int:
    """CJK 感知的粗略 token 估算（见模块 docstring）。"""
    cjk = sum(1 for char in text if _is_cjk(char))
    return max(1, cjk + (len(text) - cjk) // _DIVISOR)
