"""三入口激活契约（pet-core）。

/pet 斜杠命令（候选来自 UIAPILayer.list_tools()，不进内核接口）、
pet <verb> CLI argv（cli-ops-interface CommandGroup 扩展）、WebUI 自然语言
激活（消息驱动会话，Agent 理解意图）最终都落到同一 PetSession 生命周期，
避免各自实现激活逻辑产生第二真源。

对应接口：doc/03-interfaces/pet-mode-interface.md §3
"""

from __future__ import annotations

from collections.abc import Callable

from core.loop import LoopPlugin
from core.memory import MemoryStore

from .layers import ExplorerLayer, PersonaLayer, SafetyLayer
from .manager import PetManager
from .models import PetTask, PetTaskKind
from .session import PetSession

# /pet 斜杠命令候选 → 任务类型映射（tool_id 来自 UIAPILayer.list_tools()）。
_SLASH_TOOLS = {
    "pet.gather": PetTaskKind.INFORMATION_GATHERING,
    "pet.explore": PetTaskKind.IDLE_EXPLORATION,
}

# pet <verb> CLI argv → 任务类型映射（cli-ops CommandGroup 扩展）。
_CLI_VERBS = {
    "gather": PetTaskKind.INFORMATION_GATHERING,
    "info": PetTaskKind.INFORMATION_GATHERING,
    "explore": PetTaskKind.IDLE_EXPLORATION,
    "walk": PetTaskKind.IDLE_EXPLORATION,
}


class PetActivator:
    """三入口统一激活：均返回已启动的 PetSession，落点同一生命周期。"""

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        manager: PetManager | None = None,
        *,
        loop: LoopPlugin | None = None,
        memory: MemoryStore | None = None,
        explorer: ExplorerLayer | None = None,
        safety: SafetyLayer | None = None,
        notifier: Callable[[str], None] | None = None,
        busy: Callable[[], bool] | None = None,
    ) -> None:
        self._manager = manager if manager is not None else PetManager()
        self._loop = loop
        self._memory = memory
        self._explorer = explorer
        self._safety = safety
        self._notifier = notifier
        self._busy = busy

    def activate_from_slash(self, tool_id: str) -> PetSession:
        """`/pet` 候选来自 UIAPILayer.list_tools()，不进内核接口。"""
        kind = _SLASH_TOOLS.get(tool_id, PetTaskKind.IDLE_EXPLORATION)
        return self._activate(PetTask(kind=kind, goal=f"斜杠命令 {tool_id}"))

    def activate_from_cli(
        self, verb: str, rest: list[str], *, persona: PersonaLayer | None = None
    ) -> PetSession:
        """`pet <verb>` CLI argv 经 cli-ops CommandGroup 扩展解析；persona 从 pet.md 加载注入。"""
        kind = _CLI_VERBS.get(verb, PetTaskKind.IDLE_EXPLORATION)
        goal = " ".join(rest) if rest else f"CLI 命令 {verb}"
        return self._activate(PetTask(kind=kind, goal=goal), persona=persona)

    def activate_from_nl(self, user_input: str) -> PetSession:
        """WebUI 自然语言「启动宠物 + 任务」，Agent 理解意图后绑定任务。"""
        kind = (
            PetTaskKind.INFORMATION_GATHERING
            if "收集" in user_input or "gather" in user_input
            else PetTaskKind.IDLE_EXPLORATION
        )
        return self._activate(PetTask(kind=kind, goal=user_input))

    def _activate(self, task: PetTask, *, persona: PersonaLayer | None = None) -> PetSession:
        session = PetSession(
            persona=persona,
            loop=self._loop,
            memory=self._memory,
            explorer=self._explorer,
            safety=self._safety,
            notifier=self._notifier,
            busy=self._busy,
        )
        session.start(task)
        self._manager.register(session)
        return session
