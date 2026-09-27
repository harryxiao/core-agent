"""多宠物管理（pet-core）。

R8：同时管理多只宠物，每只独立会话/独立人格/独立任务队列，互不干扰、
可独立启停；A 宠物异常不影响 B 宠物。

对应规格：doc/openspec/specs/pet-mode/spec.md（Multi-Pet Management）
"""

from __future__ import annotations

from .models import PetTask
from .session import PetSession


class PetManager:
    """多宠物注册表：独立启停与故障隔离。"""

    def __init__(self) -> None:
        self._pets: dict[str, PetSession] = {}

    def register(self, pet: PetSession) -> None:
        """注册一只宠物（按 session_id 索引）。"""
        self._pets[pet.session_id] = pet

    def get(self, session_id: str) -> PetSession | None:
        """按会话 ID 取宠物。"""
        return self._pets.get(session_id)

    def list(self) -> list[PetSession]:
        """当前注册的全部宠物。"""
        return list(self._pets.values())

    def start(self, session_id: str, task: PetTask) -> None:
        """独立启动指定宠物。"""
        pet = self._pets.get(session_id)
        if pet is not None:
            pet.start(task)

    def stop(self, session_id: str) -> None:
        """独立终止指定宠物。"""
        pet = self._pets.get(session_id)
        if pet is not None:
            pet.terminate()

    def remove(self, session_id: str) -> None:
        """注销一只宠物。"""
        self._pets.pop(session_id, None)
