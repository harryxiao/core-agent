"""部署与托管数据模型（deployment）。

承载部署抽象数据流：RuntimeConfig / DeployTarget（运行环境）→ ReleaseInfo
（发布版本）→ HealthStatus（探活）→ ClientConnection / Session（Harness Host 会话）。

对应接口：doc/03-interfaces/deployment-interface.md §5/§6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass
class DeployTarget:
    """运行目标（PC / 服务器 / 边缘设备 / 用户自有云），抽象不锁具体选型。"""

    host: str
    runtime: str  # 进程级 | 容器级


@dataclass
class RuntimeConfig:
    """声明式运行环境配置。"""

    kind: str  # self-hosted | byoc-cloud
    target: DeployTarget
    env: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class ReleaseInfo:
    """发布版本信息。"""

    version: str
    hash: str  # 内容哈希，保证跨环境一致
    strategy: str = "rolling"  # 滚动升级策略


@dataclass
class HealthStatus:
    """健康状态：探活结果 + 失败原因 / 告警信息。"""

    alive: bool
    detail: str = ""


@dataclass
class ClientConnection:
    """接入 Harness Host 的客户端连接。"""

    client_id: str


class SessionState(StrEnum):
    """客户端会话状态。"""

    CONNECTED = "connected"
    IDLE = "idle"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"


@dataclass
class Session:
    """Harness Host 上某个客户端的独立会话（互不串扰）。"""

    session_id: str
    client_id: str
    state: SessionState = SessionState.CONNECTED
    last_seen: float = 0.0
