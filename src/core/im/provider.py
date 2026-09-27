"""IM 平台 Provider 适配器（im）。

新增平台仅需实现 IMProvider 并注册，内核 loop/工具链/记忆/权限链路零改动。
真实平台 SDK（Telegram/Discord/飞书/微信）未接，测试注入 fake。

对应接口：doc/03-interfaces/im-interface.md §3
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .models import Message, Session

if TYPE_CHECKING:
    from .gateway import IMGateway


class IMProvider(Protocol):
    """平台适配器：start 拉起、send 回推、identity 身份提取。"""

    platform: str

    def start(self, gateway: IMGateway) -> None: ...

    def send(self, session: Session, text: str) -> None: ...

    def identity(self, msg: Message) -> str: ...
