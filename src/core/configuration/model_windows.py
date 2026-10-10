"""已知模型上下文窗口表（change 0184 / ADR-0175 / 台账 E121）。

``llm.context_window`` 未配置（``0``）时，token 预算此前**恒**回落内置缺省 ``65536`` ——
与跑的是 ``gpt-4o``（128k）还是 ``claude-*``（200k）无关。本模块给出**小而有据**的
「模型名子串 → 窗口」表，供 ``loop_limits()`` 在未显式配置窗口时推导，使预算贴近模型真实窗口。

纪律（规格「LLM 提供商配置（必选）」）：

- 只收录**有据可查**的常见模型族，**不猜测**未收录模型（``known_window`` 返回 ``0`` = 不知道）；
- 表**不引入配置键**（无 CLI / env / yaml 面），故**不是**第二真源；
- 显式 ``llm.context_window > 0`` 永远**优先**于本表（用户显式声明胜出）。
"""

from __future__ import annotations

# 有序「模型名子串 → 上下文窗口」表 —— **顺序即特异性**：更具体的前缀须排在更笼统的前缀之前
# （如 `gpt-4o` 在 `gpt-4` 之前），首个命中胜出；故用 tuple 而非 dict（字典序不表达优先级）。
_KNOWN_CONTEXT_WINDOWS: tuple[tuple[str, int], ...] = (
    ("claude", 200_000),  # Anthropic Claude 3/4 系（Messages API 窗口上限）
    ("gpt-4o", 128_000),  # OpenAI GPT-4o 系
    ("gpt-4.1", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-3.5", 16_385),
    ("deepseek", 65_536),  # DeepSeek V3 / R1 系
    ("glm-4", 128_000),  # 智谱 GLM-4 系
)


def known_window(model: str) -> int:
    """按模型名**子串**推导上下文窗口（大小写不敏感，忽略首尾空白）。

    未命中 ⇒ ``0``（「不知道」的诚实表达）—— 调用方据此**不**做窗口派生、回落内置缺省，
    避免为未收录模型编造数字。
    """
    name = model.strip().lower()
    if not name:
        return 0
    for needle, window in _KNOWN_CONTEXT_WINDOWS:
        if needle in name:
            return window
    return 0
