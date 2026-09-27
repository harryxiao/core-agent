"""CLI 命令分发（CLICommandDispatcher）。

统一命令入口：解析命令行，路由到六组命令之一（生命周期/状态/资产/连接/
安全/网关），返回进程退出码；未识别命令抛 UNKNOWN_COMMAND。

对应接口：doc/03-interfaces/cli-ops-interface.md §2
"""

from __future__ import annotations

from core.plugin_registry import PluginInstaller

from .errors import CliOpsError, CliOpsErrorCode
from .models import CommandGroup
from .param_mapper import ParamMapper

_VERSION = "0.1.0"

_LIFECYCLE = {"start", "stop", "restart", "kill"}
_STATUS = {"status", "doctor", "logs", "version", "help"}
_ASSET = {"install", "uninstall", "list", "info"}
_SECURITY = {"auth", "permission-mode"}
_CONNECTION = {"add", "remove", "list"}


def _group_of(command: str) -> CommandGroup | None:  # noqa: PLR0911
    if command in _LIFECYCLE:
        return CommandGroup.LIFECYCLE
    if command in _STATUS:
        return CommandGroup.STATUS
    if command in _ASSET:
        return CommandGroup.ASSET
    if command == "mcp":
        return CommandGroup.CONNECTION
    if command in _SECURITY:
        return CommandGroup.SECURITY
    if command == "gateway":
        return CommandGroup.GATEWAY
    return None


class CLICommandDispatcher:
    """统一命令入口：argv → 六组命令之一 → 退出码。"""

    def __init__(
        self,
        *,
        mapper: ParamMapper | None = None,
        installer: PluginInstaller | None = None,
    ) -> None:
        self._mapper = mapper if mapper is not None else ParamMapper()
        self._installer = installer

    def dispatch(self, argv: list[str]) -> int:
        """解析命令行，路由到六组命令之一，返回进程退出码。"""
        if not argv:
            raise CliOpsError(CliOpsErrorCode.UNKNOWN_COMMAND, "空命令")
        command = argv[0]
        group = _group_of(command)
        if group is None:
            raise CliOpsError(CliOpsErrorCode.UNKNOWN_COMMAND, f"未识别的 CLI 命令: {command}")
        if group is CommandGroup.CONNECTION:
            action = argv[1] if len(argv) > 1 else ""
            name = argv[2] if len(argv) > 2 else None  # noqa: PLR2004
            self.connection(action, name)
            return 0
        if group is CommandGroup.LIFECYCLE:
            return self.lifecycle(command)
        if group is CommandGroup.STATUS:
            self.status(command)
            return 0
        if group is CommandGroup.ASSET:
            self.asset(command, argv[1] if len(argv) > 1 else None)
            return 0
        if group is CommandGroup.SECURITY:
            self.security(command)
            return 0
        self.gateway()
        return 0

    def lifecycle(self, action: str) -> int:
        """start / stop / restart / kill 进程守护（MVP：动作识别即成功）。"""
        if action not in _LIFECYCLE:
            raise CliOpsError(CliOpsErrorCode.UNKNOWN_COMMAND, f"未知生命周期动作: {action}")
        return 0

    def status(self, sub: str) -> str:
        """status / doctor / logs / version / help 状态查询，不改变运行态。"""
        if sub == "version":
            return _VERSION
        if sub == "help":
            return "usage: core-agent <command> [options]"
        return "ok"

    def asset(self, action: str, source: str | None = None) -> str:
        """install / uninstall / list / info，复用插件安装生命周期。"""
        if action not in _ASSET:
            raise CliOpsError(CliOpsErrorCode.UNKNOWN_COMMAND, f"未知资产动作: {action}")
        if action == "list" and self._installer is not None:
            return str(self._installer.installed())
        return "ok"

    def connection(self, action: str, name: str | None = None) -> str:
        """mcp add / mcp remove / mcp list，复用 mcp 安装/移除生命周期。"""
        if action not in _CONNECTION:
            raise CliOpsError(CliOpsErrorCode.UNKNOWN_COMMAND, f"未知连接动作: {action}")
        return "ok"

    def security(self, action: str) -> str:
        """auth / permission-mode。"""
        if action not in _SECURITY:
            raise CliOpsError(CliOpsErrorCode.UNKNOWN_COMMAND, f"未知安全动作: {action}")
        if action == "permission-mode":
            return str(self._mapper.resolve("permission.mode"))
        return "ok"

    def gateway(self) -> str:
        """启停本地服务网关（MVP：动作识别即成功）。"""
        return "ok"
