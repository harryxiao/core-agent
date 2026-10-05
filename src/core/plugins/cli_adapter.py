"""CLI 插件适配层（plugins）。

把 ``PluginKind.CLI`` 插件（manifest 携带 command/args）包装为
:class:`~core.tools.Tool`：handler 走 subprocess 真进程执行（对齐
``permission/sandbox.py`` 的 subprocess 后端模式），产出结构化结果字典，
超时 / 启动失败 / 非零退出码全部以 ``code`` 字段承载，不向调用方抛裸异常。

对应接口：doc/03-interfaces/plugin-registry-interface.md §8（安装资产）
"""

from __future__ import annotations

import subprocess
from typing import Any, cast

from core.plugin_registry import InstallableAsset
from core.tools import Tool, ToolDef

_DEFAULT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

_CLI_NONZERO_EXIT = "CLI_NONZERO_EXIT"
_CLI_TIMEOUT = "CLI_TIMEOUT"
_CLI_START_FAILED = "CLI_START_FAILED"


class CLIAdapter:
    """CLI 插件 → Tool 适配：subprocess 真进程执行，结构化承载结果。"""

    def adapt(self, asset: InstallableAsset) -> Tool:
        manifest = asset.manifest
        name = str(manifest.get("name") or manifest.get("plugin_id") or "cli")
        command = str(manifest["command"])
        fixed_args = [str(a) for a in cast(list[Any], manifest.get("args") or [])]
        description = str(manifest.get("description") or f"执行 CLI 命令 {command}")
        timeout_s = float(manifest.get("timeout_s") or 30.0)

        def handler() -> dict[str, Any]:
            try:
                proc = subprocess.run(
                    [command, *fixed_args],
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return {
                    "ok": False,
                    "code": _CLI_TIMEOUT,
                    "stdout": "",
                    "stderr": "执行超时",
                    "returncode": None,
                }
            except OSError as exc:
                return {
                    "ok": False,
                    "code": _CLI_START_FAILED,
                    "stdout": "",
                    "stderr": str(exc),
                    "returncode": None,
                }
            return {
                "ok": proc.returncode == 0,
                "code": None if proc.returncode == 0 else _CLI_NONZERO_EXIT,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
            }

        return Tool(
            definition=ToolDef(
                tool_id=f"cli.{name}",
                description=description,
                schema=_DEFAULT_SCHEMA,
                # change 0108 / 账本 E34：handler 走 subprocess 真派生进程 ⇒ 须声明 process:spawn
                # （对齐 code_run）。空声明会被 MCP 默认暴露面判据视为只读 ⇒ cli.* 默认对外暴露。
                coeffects=["process:spawn"],
                reversible=False,
                timeout_s=timeout_s,
            ),
            handler=handler,
        )
