"""三入口激活契约（beast-mode，接入层）。

/summon、/recall 斜杠命令（候选来自统一 API list_tools，不进内核接口）、
summon <beast> [task]、recall <beast> CLI argv（cli-ops CommandGroup 扩展）、
WebUI 自然语言「召唤 X 兽做 Y」/「召回 X 兽」（Agent 理解意图）最终都落到同一
BeastSession 生命周期，避免各自实现激活/复位逻辑产生第二真源。

对应规格：doc/openspec/specs/beast-mode/spec.md（Three-Entry Activation / Manual Recall）
"""

from __future__ import annotations

from .manager import BeastManager
from .session import BeastSession

# /summon /recall 斜杠候选 → 动作映射（tool_id 来自统一 API list_tools，不进内核接口）。
_SLASH_TOOLS = {
    "beast.summon": "summon",
    "beast.recall": "recall",
}

# summon / recall CLI 动词 → 动作映射（cli-ops CommandGroup 扩展，beast list 走只读名册）。
_CLI_VERBS = {
    "summon": "summon",
    "recall": "recall",
}


def _resolve_nl(user_input: str) -> str:
    """从自然语言提取神兽名（骨架启发式，Agent 理解意图 deferred）。"""
    text = user_input.strip()
    for prefix in ("召唤", "召回"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text.split()[0] if text else ""


class BeastActivator:
    """三入口统一激活/复位：均落到同一 BeastManager，同一生命周期。"""

    def __init__(self, manager: BeastManager | None = None) -> None:
        self._manager = manager if manager is not None else BeastManager()

    async def activate_from_slash(self, target: str, task: str = "") -> BeastSession:
        """`/summon <beast>` 候选来自统一 API list_tools，target 为神兽别名。"""
        return await self._manager.summon(target, task)

    async def activate_from_cli(self, beast: str, rest: list[str]) -> BeastSession:
        """`summon <beast> [task]` CLI argv 经 cli-ops CommandGroup 扩展解析。"""
        return await self._manager.summon(beast, " ".join(rest))

    async def activate_from_nl(self, user_input: str) -> BeastSession:
        """WebUI 自然语言「召唤 X 兽做 Y」，Agent 理解意图后绑定任务。"""
        return await self._manager.summon(_resolve_nl(user_input), user_input)

    def recall_from_slash(self, target: str) -> BeastSession:
        """`/recall <beast>` 候选来自统一 API list_tools，target 为神兽别名。"""
        return self._manager.recall(target)

    def recall_from_cli(self, beast: str) -> BeastSession:
        """`recall <beast>` CLI argv 经 cli-ops CommandGroup 扩展解析。"""
        return self._manager.recall(beast)

    def recall_from_nl(self, user_input: str) -> BeastSession:
        """WebUI 自然语言「召回 X 兽」，Agent 理解意图后复位目标兽。"""
        return self._manager.recall(_resolve_nl(user_input))
