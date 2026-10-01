"""部署与托管层（deployment）—— 自托管 / 云托管 BYOC + 发布升级 + Harness Host。

回答「跑在哪、怎么跑、怎么升级」：运行环境抽象（不锁容器/VM/进程）、版本化发布
与升级回滚、健康探活与生命周期、常驻 Host 多客户端接入。与 composition（装什么）、
distributed（和谁协作）正交。对应规格 `openspec/specs/deployment/spec.md`。
"""

from .cloud import CloudAdapter
from .environment import EnvironmentState, RuntimeEnvironment
from .errors import DeploymentError, DeploymentErrorCode
from .host import HarnessHost
from .lifecycle import LifecycleController, LifecycleState
from .models import (
    ClientConnection,
    DeployTarget,
    HealthStatus,
    ReleaseInfo,
    RuntimeConfig,
    Session,
    SessionState,
)
from .release import ReleaseManager
from .serve_state import ServeStateStore

__all__ = [
    "ClientConnection",
    "CloudAdapter",
    "DeployTarget",
    "DeploymentError",
    "DeploymentErrorCode",
    "EnvironmentState",
    "HarnessHost",
    "HealthStatus",
    "LifecycleController",
    "LifecycleState",
    "ReleaseInfo",
    "ReleaseManager",
    "RuntimeConfig",
    "RuntimeEnvironment",
    "ServeStateStore",
    "Session",
    "SessionState",
]
