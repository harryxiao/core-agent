"""A2A Client（distributed）。

作为 Client 委派任务给外部 Agent：发现对端 AgentCard（验签）、校验协议绑定与
最小权限 scope、经传输发送任务（幂等去重），并订阅进度。

对应接口：doc/03-interfaces/distributed-interface.md §1
"""

from __future__ import annotations

from collections.abc import Callable

from .connection import ConnectionManager
from .errors import DistributedError, DistributedErrorCode
from .models import AgentCard, Stream, Task, TaskHandle


class A2AClient:
    """A2A 客户端：委派任务给外部 Agent。"""

    def __init__(  # noqa: PLR0913 — 传输/鉴权/发现均为构造注入
        self,
        *,
        verifier: Callable[[str, bytes], bool] | None = None,
        cards: dict[str, AgentCard] | None = None,
        policy: Callable[[str, str], bool] | None = None,
        authenticator: Callable[[AgentCard], bool] | None = None,
        transport: Callable[[AgentCard, Task], TaskHandle] | None = None,
        supported_protocols: set[str] | None = None,
        connections: ConnectionManager | None = None,
    ) -> None:
        self._verifier: Callable[[str, bytes], bool] = (
            verifier if verifier is not None else lambda _sig, _data: True
        )
        self._cards: dict[str, AgentCard] = cards if cards is not None else {}
        self._policy: Callable[[str, str], bool] = (
            policy if policy is not None else lambda _target, _peer: True
        )
        self._authenticator: Callable[[AgentCard], bool] = (
            authenticator if authenticator is not None else lambda _card: True
        )
        self._transport: Callable[[AgentCard, Task], TaskHandle] = (
            transport
            if transport is not None
            else lambda _card, task: TaskHandle(task_id=task.task_id, peer=task.target)
        )
        self._supported = supported_protocols if supported_protocols is not None else {"json-rpc"}
        self._connections = connections if connections is not None else ConnectionManager()
        self._sent: dict[str, TaskHandle] = {}

    def read_card(self, peer: str) -> AgentCard:
        """读取并验签对端 AgentCard；不可达/签名无效分别抛对应错误码。"""
        card = self._cards.get(peer)
        if card is None:
            raise DistributedError(
                DistributedErrorCode.A2A_PEER_UNREACHABLE,
                f"对端 Agent {peer} 不可达",
            )
        if not card.verify(self._verifier):
            raise DistributedError(
                DistributedErrorCode.A2A_CARD_INVALID,
                f"对端 Agent {peer} 卡片签名无效",
            )
        return card

    def send_message(self, target: AgentCard, task: Task) -> TaskHandle:
        """委派任务：协议绑定 → 鉴权 → 最小权限 → 幂等去重 → 传输。"""
        peer = target.provider.name
        if target.interface is None or target.interface.protocol not in self._supported:
            raise DistributedError(
                DistributedErrorCode.A2A_PROTOCOL_UNSUPPORTED,
                f"对端 {peer} 声明的绑定不被支持",
            )
        if not self._authenticator(target):
            raise DistributedError(
                DistributedErrorCode.A2A_AUTH_FAILED,
                f"对端 {peer} 鉴权失败",
            )
        if not self._policy(task.target, peer):
            raise DistributedError(
                DistributedErrorCode.A2A_SCOPE_DENIED,
                f"调用 {task.target} 超出对端 {peer} 已授权 scope",
            )
        if task.task_id in self._sent:
            return self._sent[task.task_id]  # 委派重试幂等：同 ID 返回首次结果
        try:
            handle = self._transport(target, task)
        except DistributedError:
            raise
        except Exception as exc:  # noqa: BLE001 — 传输层任意异常统一归为对端不可达
            raise DistributedError(
                DistributedErrorCode.A2A_PEER_UNREACHABLE,
                f"向对端 {peer} 发送任务失败",
            ) from exc
        self._connections.heartbeat(peer)
        self._sent[task.task_id] = handle
        return handle

    def subscribe(self, handle: TaskHandle) -> Stream:
        """订阅任务进度（流式 / 推送）。"""
        return Stream(handle=handle)
