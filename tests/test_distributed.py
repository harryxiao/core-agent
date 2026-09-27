"""distributed 单元测试（对齐契约红线：卡片签名验证 / 双向认证 + 最小权限 / 幂等 / 6 错误码）。"""

from __future__ import annotations

from typing import Any

import pytest

from core.distributed import (
    A2AClient,
    A2AServer,
    AgentCard,
    AgentInterface,
    AgentProvider,
    ConnectionManager,
    ConnectionState,
    DistributedError,
    DistributedErrorCode,
    DistributedGateway,
    Task,
    TaskHandle,
)


def _signer(data: bytes) -> str:
    return "sig:" + data.decode("utf-8")


def _verifier(signature: str, data: bytes) -> bool:
    return signature == "sig:" + data.decode("utf-8")


def _card(name: str) -> AgentCard:
    return AgentCard(
        provider=AgentProvider(name=name), interface=AgentInterface(protocol="json-rpc")
    )


def _fail_tool(target: str, payload: dict[str, Any]) -> object:
    raise RuntimeError("tool failed")  # noqa: TRY003


# ---- 卡片签名验证 ----


def test_read_card_valid_signature() -> None:
    card = _card("peer-a").sign(_signer)
    client = A2AClient(verifier=_verifier, cards={"peer-a": card})
    assert client.read_card("peer-a") is card


def test_read_card_invalid_signature() -> None:
    client = A2AClient(verifier=_verifier, cards={"peer-a": _card("peer-a")})
    with pytest.raises(DistributedError) as exc_info:
        client.read_card("peer-a")
    assert exc_info.value.code is DistributedErrorCode.A2A_CARD_INVALID


def test_read_card_peer_unreachable() -> None:
    client = A2AClient(verifier=_verifier, cards={})
    with pytest.raises(DistributedError) as exc_info:
        client.read_card("ghost")
    assert exc_info.value.code is DistributedErrorCode.A2A_PEER_UNREACHABLE


# ---- 双向认证 + 最小权限 ----


def test_send_message_scope_denied() -> None:
    client = A2AClient(policy=lambda target, peer: False)
    with pytest.raises(DistributedError) as exc_info:
        client.send_message(_card("peer-a"), Task(task_id="t1", target="filesystem"))
    assert exc_info.value.code is DistributedErrorCode.A2A_SCOPE_DENIED


def test_send_message_auth_failed() -> None:
    client = A2AClient(authenticator=lambda card: False)
    with pytest.raises(DistributedError) as exc_info:
        client.send_message(_card("peer-a"), Task(task_id="t1", target="filesystem"))
    assert exc_info.value.code is DistributedErrorCode.A2A_AUTH_FAILED


def test_send_message_protocol_unsupported() -> None:
    card = AgentCard(
        provider=AgentProvider(name="peer-a"), interface=AgentInterface(protocol="grpc")
    )
    client = A2AClient(supported_protocols={"json-rpc"})
    with pytest.raises(DistributedError) as exc_info:
        client.send_message(card, Task(task_id="t1", target="x"))
    assert exc_info.value.code is DistributedErrorCode.A2A_PROTOCOL_UNSUPPORTED


def test_send_message_transport_failure_peer_unreachable() -> None:
    def _boom(card: AgentCard, task: Task) -> TaskHandle:
        raise RuntimeError("network down")  # noqa: TRY003

    client = A2AClient(transport=_boom)
    with pytest.raises(DistributedError) as exc_info:
        client.send_message(_card("peer-a"), Task(task_id="t1", target="x"))
    assert exc_info.value.code is DistributedErrorCode.A2A_PEER_UNREACHABLE


def test_server_report_task_failed() -> None:
    server = A2AServer(tool_caller=_fail_tool)
    handle = server.on_message(Task(task_id="t1", target="x"))
    with pytest.raises(DistributedError) as exc_info:
        server.report(handle)
    assert exc_info.value.code is DistributedErrorCode.A2A_TASK_FAILED


# ---- 委派重试幂等 ----


def test_client_retry_idempotent() -> None:
    calls: list[str] = []

    def _transport(card: AgentCard, task: Task) -> TaskHandle:
        calls.append(task.task_id)
        return TaskHandle(task_id=task.task_id, peer=task.target)

    client = A2AClient(transport=_transport)
    first = client.send_message(_card("peer-a"), Task(task_id="t1", target="x"))
    second = client.send_message(_card("peer-a"), Task(task_id="t1", target="x"))
    assert first is second
    assert calls == ["t1"]


def test_server_dedup_same_task_id() -> None:
    server = A2AServer()
    first = server.on_message(Task(task_id="t1", target="x"))
    second = server.on_message(Task(task_id="t1", target="x"))
    assert first is second


# ---- 端到端双向互调 ----


def test_end_to_end_delegate() -> None:
    server = A2AServer(
        card=_card("self"), signer=_signer, tool_caller=lambda target, payload: f"result:{target}"
    )
    client = A2AClient(verifier=_verifier, transport=lambda card, task: server.on_message(task))
    handle = client.send_message(server.expose(), Task(task_id="t1", target="filesystem"))
    server.report(handle)
    assert handle.status == "done"
    assert handle.result == "result:filesystem"


# ---- 连接管理：心跳 / 重连 / 超时 / 释放 ----


def test_connection_reconnect_and_release() -> None:
    manager = ConnectionManager(max_retries=2)
    conn = manager.connect("peer-a")
    assert conn.state is ConnectionState.CONNECTED
    manager.reconnect("peer-a")
    assert conn.state is ConnectionState.RECONNECTING
    assert manager.backoff("peer-a") == 1.0
    manager.reconnect("peer-a")
    manager.reconnect("peer-a")
    assert conn.state is ConnectionState.DISCONNECTED
    manager.release("peer-a")
    assert conn.state is ConnectionState.CLOSED


def test_connection_heartbeat_and_timeout() -> None:
    now = [0.0]
    manager = ConnectionManager(clock=lambda: now[0])
    manager.connect("peer-a")
    assert manager.is_alive("peer-a", timeout=10.0)
    now[0] = 100.0
    assert not manager.is_alive("peer-a", timeout=10.0)
    assert manager.heartbeat("peer-a")
    assert manager.is_alive("peer-a", timeout=10.0)


# ---- 网关：协议绑定 / P2P 直连优先 ----


def test_gateway_route_direct_and_relay() -> None:
    gateway = DistributedGateway()
    assert gateway.route("json-rpc", p2p=True) == "direct"
    assert gateway.route("grpc") == "relay"
    with pytest.raises(DistributedError) as exc_info:
        gateway.route("unknown")
    assert exc_info.value.code is DistributedErrorCode.A2A_PROTOCOL_UNSUPPORTED
