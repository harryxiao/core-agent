"""云托管 BYOC 适配（deployment）。

云托管与自托管共享同一部署抽象与配置：adapt 将部署抽象映射到用户自有云，
parity_check 校验自托管与云托管行为一致（同一 runtime 抽象）。

对应接口：doc/03-interfaces/deployment-interface.md §2
"""

from __future__ import annotations

from .environment import RuntimeEnvironment
from .models import DeployTarget, RuntimeConfig


class CloudAdapter:
    """云托管 BYOC 适配器。"""

    def adapt(self, target: DeployTarget) -> RuntimeEnvironment:
        """将部署抽象映射到用户自有云，返回可装配的运行环境。"""
        env = RuntimeEnvironment()
        env.configure(RuntimeConfig(kind="byoc-cloud", target=target))
        return env

    def parity_check(self, local: RuntimeConfig, cloud: RuntimeConfig) -> bool:
        """自托管与云托管共享同一部署抽象（runtime 一致）即行为一致。"""
        return local.target.runtime == cloud.target.runtime
