"""分布式协作数据模型（distributed）。

承载 A2A 交互数据流：AgentCard（身份 + 能力 + 接口 + 签名）→ Task（委派任务）
→ TaskHandle（任务句柄）→ Stream（进度订阅）。

对应接口：doc/03-interfaces/distributed-interface.md §3
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentProvider:
    """Agent 提供方身份。"""

    name: str
    url: str = ""
    description: str = ""


@dataclass
class AgentCapability:
    """Agent 能力声明。"""

    name: str
    description: str = ""


@dataclass
class AgentSkill:
    """Agent 技能声明。"""

    name: str
    description: str = ""


@dataclass
class AgentInterface:
    """Agent 交互接口声明：协议绑定 + 端点 + 鉴权方案。"""

    protocol: str  # json-rpc | grpc | rest
    endpoint: str = ""
    authentication: str = ""  # oauth2 | mtls | apikey | oidc


@dataclass
class AgentCard:
    """Agent 名片：声明身份、能力、技能与接口；签名验证通过才接受。"""

    provider: AgentProvider
    capabilities: list[AgentCapability] = field(default_factory=list[AgentCapability])
    skills: list[AgentSkill] = field(default_factory=list[AgentSkill])
    interface: AgentInterface | None = None
    signature: str | None = None

    def sign(self, signer: Callable[[bytes], str]) -> AgentCard:
        """对卡片内容签名（签名经注入回调，不落地真实密钥）。"""
        self.signature = signer(self._canonical().encode("utf-8"))
        return self

    def verify(self, verifier: Callable[[str, bytes], bool]) -> bool:
        """验证卡片签名；未签名视为无效。"""
        if self.signature is None:
            return False
        return verifier(self.signature, self._canonical().encode("utf-8"))

    def _canonical(self) -> str:
        """卡片内容的确定性序列化（签名 / 验签一致）。"""
        caps = ",".join(sorted(f"{c.name}:{c.description}" for c in self.capabilities))
        skills = ",".join(sorted(f"{s.name}:{s.description}" for s in self.skills))
        iface = ""
        if self.interface is not None:
            iface = f"{self.interface.protocol}@{self.interface.endpoint}"
        return "|".join([self.provider.name, self.provider.url, caps, skills, iface])


@dataclass
class Task:
    """委派任务：携带幂等 ID，对端按 ID 去重。"""

    task_id: str
    target: str  # 目标能力 / 技能
    payload: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class TaskHandle:
    """任务句柄：跟踪委派任务的执行状态与结果。"""

    task_id: str
    peer: str
    status: str = "pending"  # pending | running | done | failed
    result: Any = None


@dataclass
class Stream:
    """进度订阅流：承载流式 / 推送事件。"""

    handle: TaskHandle
    events: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])

    def push(self, event: dict[str, Any]) -> None:
        """推入一条进度事件。"""
        self.events.append(event)

    def next(self) -> dict[str, Any] | None:
        """取出下一条事件（无则返回 None）。"""
        return self.events.pop(0) if self.events else None
