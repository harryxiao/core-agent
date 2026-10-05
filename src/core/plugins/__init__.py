"""插件安装接线（plugins）。

CLI 插件适配层 + 按 ``PluginKind`` 分发的真实 resolver/installer，供组合根
注入 ``PluginInstaller``，替换 ``plugin_registry.installable`` 的空壳默认值，
使「外部插件安装 → 按 kind 分发 → 可被 ToolProvider 调用」链路贯通。
"""

from .cli_adapter import CLIAdapter
from .install import InstallDispatcher
from .installs import (
    InstallRecord,
    PluginInstallRegistry,
    PluginInstallStore,
    default_install_store,
    plugin_installs_path,
)
from .sources import (
    MANIFEST_FILENAME,
    Cloner,
    Fetcher,
    resolve_git_repo,
    resolve_market_registry,
    resolve_mcp_endpoint,
)

__all__ = [
    "MANIFEST_FILENAME",
    "CLIAdapter",
    "Cloner",
    "Fetcher",
    "InstallDispatcher",
    "InstallRecord",
    "PluginInstallRegistry",
    "PluginInstallStore",
    "default_install_store",
    "plugin_installs_path",
    "resolve_git_repo",
    "resolve_market_registry",
    "resolve_mcp_endpoint",
]
