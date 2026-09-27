"""分布式网关（distributed）。

拓扑接入 + 传输管理：默认 JSON-RPC 绑定、gRPC/REST 备选；P2P 打洞直连优先、
失败回退 relay（仅传输层优化，不改上层 A2A 协议行为）。

对应接口：doc/03-interfaces/distributed-interface.md §4
"""

from __future__ import annotations

from .errors import DistributedError, DistributedErrorCode
from .models import AgentCard


class DistributedGateway:
    """拓扑接入与传输管理。"""

    DEFAULT_BINDINGS = {"json-rpc": "http", "grpc": "http2", "rest": "http"}

    def __init__(self, *, bindings: dict[str, str] | None = None) -> None:
        self._bindings = bindings if bindings is not None else dict(self.DEFAULT_BINDINGS)
        self._peers: dict[str, AgentCard] = {}

    def register(self, peer: str, card: AgentCard) -> None:
        """登记对端卡片（拓扑接入）。"""
        self._peers[peer] = card

    def discover(self, peer: str) -> AgentCard | None:
        """按名发现对端卡片。"""
        return self._peers.get(peer)

    def supports(self, protocol: str) -> bool:
        """判断协议绑定是否被支持。"""
        return protocol in self._bindings

    def route(self, protocol: str, *, p2p: bool = False) -> str:
        """选择传输路径：不支持抛 PROTOCOL_UNSUPPORTED；P2P 打洞直连优先，否则 relay。"""
        if not self.supports(protocol):
            raise DistributedError(
                DistributedErrorCode.A2A_PROTOCOL_UNSUPPORTED,
                f"协议绑定 {protocol} 不被支持",
            )
        return "direct" if p2p else "relay"
