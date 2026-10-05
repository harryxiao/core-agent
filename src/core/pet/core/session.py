"""宠物会话生命周期（pet-core）。

PetSession 是编排层「后台自治循环」核心句柄：启动 / 休眠 / 恢复 / 异常退避 /
终止全生命周期收口；每次唤醒复用 Loop.run() 同步薄壳逐次执行；让行复用
orchestration 任务状态机 SUSPENDED 语义（宠物自身仅四态，不新增枚举）；
偏好以 MemoryEntry.source="user" 落 L2 facts 层。

对应接口：doc/03-interfaces/pet-mode-interface.md §1
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Callable
from typing import Any, cast

from core.loop import DefaultLoop, LoopPlugin, LoopResult
from core.memory import MemoryEntry, MemoryStore

from .errors import PetError, PetErrorCode
from .layers import ExplorerLayer, PersonaLayer, SafetyLayer
from .models import PetSessionState, PetTask, PetTaskKind


class PetSession:
    """宠物会话：低优先级后台自治任务的生命周期与派发。"""

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        *,
        session_id: str | None = None,
        loop: LoopPlugin | None = None,
        memory: MemoryStore | None = None,
        persona: PersonaLayer | None = None,
        explorer: ExplorerLayer | None = None,
        safety: SafetyLayer | None = None,
        notifier: Callable[[str], None] | None = None,
        busy: Callable[[], bool] | None = None,
        feedback_period: int = 5,
    ) -> None:
        self.session_id = session_id if session_id is not None else uuid.uuid4().hex
        self.state = PetSessionState.IDLE
        self._loop = loop if loop is not None else DefaultLoop()
        self._memory = memory
        self._persona = persona
        self._explorer = explorer
        self._safety = safety
        self._notifier = notifier
        self._busy = busy if busy is not None else (lambda: False)
        self._feedback_period = feedback_period
        self._tasks: deque[PetTask] = deque()
        self._yielding = False
        self._fault = ""
        self._wake_count = 0
        self._last_trace_id = ""
        self._preferences: dict[str, str] = {}

    # ---- 快照 / 恢复（注册表落盘用） ----

    def snapshot(self) -> dict[str, Any]:
        """序列化会话可持久化态（id/状态/故障/让行/唤醒计数/偏好/任务队列）。"""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "fault": self._fault,
            "yielding": self._yielding,
            "wake_count": self._wake_count,
            "preferences": dict(self._preferences),
            "tasks": [
                {"kind": task.kind.value, "goal": task.goal, "priority": task.priority}
                for task in self._tasks
            ],
        }

    @classmethod
    def restore(  # noqa: PLR0913 — 恢复面与 __init__ 注入面对称
        cls,
        record: dict[str, Any],
        *,
        loop: LoopPlugin | None = None,
        memory: MemoryStore | None = None,
        persona: PersonaLayer | None = None,
        explorer: ExplorerLayer | None = None,
        safety: SafetyLayer | None = None,
        notifier: Callable[[str], None] | None = None,
        busy: Callable[[], bool] | None = None,
        feedback_period: int = 5,
    ) -> PetSession:
        """从快照恢复会话（保留 id/状态/任务/偏好/唤醒计数）；依赖可再注入（缺省回退兜底）。"""
        session = cls(
            session_id=record.get("session_id"),
            loop=loop,
            memory=memory,
            persona=persona,
            explorer=explorer,
            safety=safety,
            notifier=notifier,
            busy=busy,
            feedback_period=feedback_period,
        )
        session.state = PetSessionState(record.get("state", PetSessionState.IDLE.value))
        session._fault = str(record.get("fault", ""))
        session._yielding = bool(record.get("yielding", False))
        session._wake_count = int(record.get("wake_count", 0))
        raw_preferences = cast("dict[str, Any]", record.get("preferences") or {})
        session._preferences = {str(k): str(v) for k, v in raw_preferences.items()}
        raw_tasks = cast("list[dict[str, Any]]", record.get("tasks") or [])
        session._tasks = deque(
            PetTask(
                kind=PetTaskKind(task["kind"]),
                goal=str(task["goal"]),
                priority=int(task.get("priority", 0)),
            )
            for task in raw_tasks
        )
        return session

    # ---- 生命周期 ----

    def start(self, task: PetTask) -> None:
        """IDLE → ACTIVE 并派发首个任务；重复激活被拒。"""
        if self.state is not PetSessionState.IDLE:
            raise PetError(PetErrorCode.PET_ALREADY_ACTIVE, "会话已激活，重复激活被拒")
        self.state = PetSessionState.ACTIVE
        self._tasks.append(task)

    def wake(self) -> LoopResult:
        """每次唤醒经 Loop.run() 同步薄壳执行一次自治任务。"""
        if self.state is PetSessionState.BACKOFF:
            raise PetError(PetErrorCode.PET_BACKOFF, "会话处于异常退避态，暂不可唤醒")
        if self.state is not PetSessionState.ACTIVE:
            raise PetError(PetErrorCode.PET_NOT_ACTIVE, "会话未激活，唤醒无效")
        if self._yielding or self._busy():
            raise PetError(PetErrorCode.PET_YIELDING, "主循环 busy，宠物让行")
        goal = self._tasks[0].goal if self._tasks else "闲逛探索：观察当前环境"
        result = self._loop.run(self._compose_prompt(goal))
        self._last_trace_id = result.trace_id
        self._wake_count += 1
        self._notify_owner()
        return result

    def suspend(self) -> None:
        """让行/休眠：复用 orchestration 任务状态机 SUSPENDED 语义，不新增枚举。"""
        self._require_active("suspend")
        self._yielding = True

    def resume(self) -> None:
        """主循环释放资源后恢复，已完成的子任务结果不丢失。"""
        self._require_active("resume")
        self._yielding = False

    def backoff(self, err: Exception) -> None:
        """异常退避：标记故障态、隔离，不残留半运行状态，不阻塞主循环。"""
        if self.state is PetSessionState.TERMINATED:
            raise PetError(PetErrorCode.PET_NOT_ACTIVE, "会话已终止，无法退避")
        self.state = PetSessionState.BACKOFF
        self._fault = str(err)

    def terminate(self) -> None:
        """终止释放：任务与资源释放，无悬空引用。"""
        self.state = PetSessionState.TERMINATED
        self._tasks.clear()
        self._yielding = False

    # ---- 任务派发 ----

    def dispatch(self, task: PetTask) -> None:
        """低优先级派发；主循环 busy 时让行，不抢锁。"""
        self._require_active("dispatch")
        self._tasks.append(task)

    # ---- 偏好追踪 ----

    def observe(self, behavior: str) -> MemoryEntry:
        """观察主人行为/反馈，以 MemoryEntry.source="user" 落 L2 facts 层。"""
        if self._memory is None:
            raise PetError(PetErrorCode.PET_PREFERENCE_WRITE_FAILED, "记忆后端未接，偏好无法落 L2")
        entry = MemoryEntry(
            id=uuid.uuid4().hex,
            layer="L2",
            content=behavior,
            tags=["preference"],
            source="user",
            trace_id=self._last_trace_id or uuid.uuid4().hex,
        )
        if self._memory.write("L2", entry) is None:
            raise PetError(PetErrorCode.PET_PREFERENCE_WRITE_FAILED, "偏好写入 L2 facts 层失败")
        if ":" in behavior:
            key, _, value = behavior.partition(":")
            self._preferences[key.strip()] = value.strip()
        return entry

    def prefer(self, key: str) -> str | None:
        """复用已记录偏好，供任务执行/沟通时对齐主人偏好。"""
        if key in self._preferences:
            return self._preferences[key]
        if self._memory is None:
            return None
        for entry in self._memory.read(key, budget=512):
            if entry.source == "user":
                return entry.content
        return None

    # ---- 反馈与惊喜 ----

    def report(self) -> str:
        """达到反馈周期时向主人汇报后台进展，不阻塞主循环。"""
        prefix = "定期反馈：" if self._on_feedback_cycle() else ""
        name = self._persona.name if self._persona is not None else self.session_id[:8]
        return f"{prefix}宠物 {name}（状态 {self.state.value}，待办 {len(self._tasks)}）"

    def surprise(self) -> str | None:
        """基于主人偏好发现可代办/取悦之事，经**真实 loop** 主动执行并制造惊喜。

        无已记录偏好（无真实可代办前提）⇒ 返回 ``None`` —— 不产出、不通知
        （账本 E26：不以「已帮你安排」通用文案谎报）；有偏好 ⇒ 真的跑一次 loop 代办，
        回报其**真实产出**。
        """
        if not self._preferences:
            return None
        key, value = next(iter(self._preferences.items()))
        goal = self._compose_prompt(f"基于主人偏好「{key}={value}」为主人代办一件小事")
        result = self._loop.run(goal)
        return f"发现可代办：{key}={value} —— {result.reply}"

    # ---- 内部辅助 ----

    def _notify_owner(self) -> None:
        """唤醒收尾向主人投递反馈与惊喜（账本 E16 / E26）。

        反馈周期命中时把既有 :meth:`report` 产出经 ``notifier`` 入队 —— notify 只入队、
        不阻塞主循环（异步投递语义由宿主侧 flush 收口）；**同节拍**再尝试惊喜，仅在有
        真实产出（非 ``None``）时追加投递。惊喜要跑一次 loop，属**非关键路径**：其失败被
        吞掉，绝不阻断唤醒收尾。无 notifier 时静默（不跑有成本的惊喜）。
        """
        if self._notifier is None or not self._on_feedback_cycle():
            return
        self._notifier(self.report())
        try:
            surprise = self.surprise()
        except Exception:  # noqa: BLE001 — 惊喜非关键路径：失败静默，不阻断唤醒
            surprise = None
        if surprise is not None:
            self._notifier(surprise)

    def _on_feedback_cycle(self) -> bool:
        """是否命中反馈周期（反馈节拍单一判据真源）。"""
        return bool(self._wake_count and self._wake_count % self._feedback_period == 0)

    def _require_active(self, op: str) -> None:
        if self.state is not PetSessionState.ACTIVE:
            raise PetError(PetErrorCode.PET_NOT_ACTIVE, f"会话未激活，{op} 无效")

    def _compose_prompt(self, goal: str) -> str:
        if self._persona is None:
            return goal
        return f"{self._persona.render_prompt()}\n任务：{goal}"
