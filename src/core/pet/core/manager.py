"""多宠物管理（pet-core）。

R8：同时管理多只宠物，每只独立会话/独立人格/独立任务队列，互不干扰、
可独立启停；A 宠物异常不影响 B 宠物。

注册表可跨进程存活：注入 `path` 时注册/启停后落盘（单文件 JSON 快照），
新进程经 `factory` 把加载的记录恢复为会话（组合根借此注入真依赖）。

对应规格：doc/openspec/specs/pet-mode/spec.md（Multi-Pet Management）
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import PetTask
from .session import PetSession


def _bare_restore(record: dict[str, Any]) -> PetSession:
    """缺省恢复：无依赖的裸会话（测试 / 无组合根的调用方）。"""
    return PetSession.restore(record)


class PetManager:
    """多宠物注册表：独立启停与故障隔离；可选跨进程落盘（路径注入）。"""

    def __init__(
        self,
        path: Path | None = None,
        *,
        factory: Callable[[dict[str, Any]], PetSession] | None = None,
    ) -> None:
        self._path = path
        self._factory = factory if factory is not None else _bare_restore
        self._pets: dict[str, PetSession] = {}
        if path is not None and path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        for record in json.loads(path.read_text(encoding="utf-8")):
            pet = self._factory(record)
            self._pets[pet.session_id] = pet

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [pet.snapshot() for pet in self._pets.values()]
        self._path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def persist(self) -> None:
        """把当前注册表快照落盘（无路径时无操作）——供驱动 tick / 控制面变更后调用。"""
        self._persist()

    def register(self, pet: PetSession) -> None:
        """注册一只宠物（按 session_id 索引）。"""
        self._pets[pet.session_id] = pet
        self._persist()

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
            self._persist()

    def stop(self, session_id: str) -> None:
        """独立终止指定宠物。"""
        pet = self._pets.get(session_id)
        if pet is not None:
            pet.terminate()
            self._persist()

    def remove(self, session_id: str) -> None:
        """注销一只宠物。"""
        self._pets.pop(session_id, None)
        self._persist()
