"""UI 界面（ui）：CLI/Web/Desktop 三模统一内核入口。"""

from .api import UIAPILayer
from .cli_bridge import CLIBridge
from .desktop_bridge import DesktopBridge
from .errors import UiError, UiErrorCode
from .models import Event
from .sessions import SessionRegistry
from .web_bridge import WebBridge

__all__ = [
    "CLIBridge",
    "DesktopBridge",
    "Event",
    "SessionRegistry",
    "UIAPILayer",
    "UiError",
    "UiErrorCode",
    "WebBridge",
]
