"""宠物控制面（pet-core）—— verb → 会话操作 + 会话寻址（change 0088）。

宿主层前台（`/pet [cmd]`、`pet <verb>` CLI argv、WebUI 自然语言）在宠物运行期间**随时**查看状态 /
停止工作 / 换一件活 / 睡觉 / 叫醒。控制面由本门面**单一收口**（CLI 与 `UIAPILayer` 复用同一实现，
避免两份 verb 分发真源）。

**作用域 = 本进程已注册会话**（跨进程注册表是快照，不驱动 live 会话 —— 有意不做跨进程）。
`status` 由 `PetSession.snapshot()` 过滤而来：**不含**主人偏好与任务正文（观测面不外泄隐私）。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（控制面）
"""

from __future__ import annotations

from typing import Any

from .errors import PetError, PetErrorCode
from .manager import PetManager
from .models import PetSessionState, PetTask, PetTaskKind
from .session import PetSession


class PetControl:
    """控制面门面：以 verb 面驱动既有会话操作，复用 `suspend`/`resume`/`dispatch`/`stop`。"""

    def __init__(self, manager: PetManager) -> None:
        self._manager = manager

    # ---- verb 面 ----

    def status(self, session_id: str | None = None) -> dict[str, Any]:
        """结构化状态（id / 状态 / 是否休眠 / 待办数 / 唤醒计数 / 故障）；不外泄偏好与任务正文。"""
        pet = self._resolve(session_id)
        snap = pet.snapshot()
        return {
            "session_id": snap["session_id"],
            "state": snap["state"],
            "sleeping": snap["yielding"],
            "pending": len(snap["tasks"]),
            "wake_count": snap["wake_count"],
            "fault": snap["fault"],
        }

    def sleep(self, session_id: str | None = None) -> str:
        """让宠物入睡/让行（复用 orchestration `SUSPENDED` 语义）。"""
        pet = self._resolve(session_id)
        pet.suspend()
        self._manager.persist()
        return f"已让宠物 {pet.session_id} 入睡（让行态）"

    # ---- 结果查询（change 0113 / E46） ----

    def result(self, session_id: str | None = None) -> dict[str, Any]:
        """最近一次任务结果的**只读**查询（会话 id / 是否有结果 / 结果正文 / 成败）。

        与 `status` 的边界：`status` 是**观测面**（不含主人偏好与任务正文，规格明文），本动词是
        **结果查询面**，**只**暴露最近一次结果的正文与成败 —— 二者互不污染（`status` 面逐字不变）。

        只作用**本进程**已注册会话、只**最近一次**、**不落盘**（不进 `snapshot`/注册表）；
        寻址复用 `_resolve`（与既有控制动词逐字一致）。
        """
        pet = self._resolve(session_id)
        last = pet.last_result
        return {
            "session_id": pet.session_id,
            "has_result": last is not None,
            "reply": last.reply if last is not None else None,
            "failed": last.failed if last is not None else None,
        }

    def wake(self, session_id: str | None = None) -> str:
        """叫醒宠物：`BACKOFF` 会话执行故障恢复，其余清让行态恢复。

        **注意**：此 `wake` 是「恢复让行/退避」，非 `PetSession.wake()`（执行一次任务）。
        """
        pet = self._resolve(session_id)
        if pet.state is PetSessionState.BACKOFF:
            pet.recover()
        else:
            pet.resume()
        self._manager.persist()
        return f"已叫醒宠物 {pet.session_id}"

    def assign(self, goal: str, *, session_id: str | None = None) -> str:
        """换一件活：派发新任务（自动唤醒让行中的宠物 —— change `0087`）。"""
        pet = self._resolve(session_id)
        pet.dispatch(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal=goal))
        pet.observe_owner(goal)  # 派发成功后观察主人原话（空 ⇒ observe_owner 自行跳过）
        self._manager.persist()
        return f"已给宠物 {pet.session_id} 派发新任务：{goal}"

    def stop(self, session_id: str | None = None) -> str:
        """停止工作（终止会话并释放）。"""
        pet = self._resolve(session_id)
        self._manager.stop(pet.session_id)
        return f"已停止宠物会话 {pet.session_id}"

    # ---- 寻址 ----

    def _resolve(self, session_id: str | None) -> PetSession:
        """会话寻址：显式 id（未知 ⇒ `PET_NOT_FOUND`）/ 单宠物默认 / 多宠物未指定 ⇒ 拒绝并列出。"""
        if session_id is not None:
            pet = self._manager.get(session_id)
            if pet is None:
                raise PetError(PetErrorCode.PET_NOT_FOUND, f"未找到宠物会话：{session_id}")
            return pet
        pets = self._manager.list()
        if not pets:
            raise PetError(PetErrorCode.PET_NOT_FOUND, "当前无注册宠物")
        if len(pets) > 1:
            ids = "、".join(pet.session_id for pet in pets)
            raise PetError(PetErrorCode.PET_TARGET_AMBIGUOUS, f"多只宠物，请指定会话 id：{ids}")
        return pets[0]
