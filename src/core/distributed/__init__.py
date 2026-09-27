"""分布式协作层（distributed）—— A2A 双向互调。

从单设备循环升级为可跨设备协作的分布式 Agent：AgentCard 发现与签名、协议绑定、
安全鉴权、多设备拓扑、可选 P2P 优化、A2A 连接管理。与 MCP 互补：Server 内部经
MCP 调工具、对外经 A2A 暴露能力。对应规格 `openspec/specs/distributed/spec.md`。
"""

from .client import A2AClient
from .connection import Connection, ConnectionManager, ConnectionState
from .errors import DistributedError, DistributedErrorCode
from .gateway import DistributedGateway
from .models import (
    AgentCapability,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    Stream,
    Task,
    TaskHandle,
)
from .server import A2AServer

__all__ = [
    "A2AClient",
    "A2AServer",
    "AgentCapability",
    "AgentCard",
    "AgentInterface",
    "AgentProvider",
    "AgentSkill",
    "Connection",
    "ConnectionManager",
    "ConnectionState",
    "DistributedError",
    "DistributedErrorCode",
    "DistributedGateway",
    "Stream",
    "Task",
    "TaskHandle",
]
