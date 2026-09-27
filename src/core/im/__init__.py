"""IM 网关（im）：多平台统一接入 + 消息驱动会话。"""

from .errors import ImError, ImErrorCode
from .gateway import IMGateway
from .models import Message, Session
from .provider import IMProvider

__all__ = ["IMGateway", "IMProvider", "ImError", "ImErrorCode", "Message", "Session"]
