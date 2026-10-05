"""MCP 端点注册表与来源解析（mcp）。

``mcp add`` 的成果必须活过**一次性 CLI 进程**（每次调用都新建 installer / client）：
端点落 ``$CORE_STATE_DIR/mcp-endpoints.json`` —— 与 ``checkpoints.jsonl`` / ``pets.json`` /
``evolution-pending.json`` 同状态目录约定，**原子写**（tmp + ``os.replace``，同 change 0062）。
组合根在**装配期**读回并经既有安装管线（``InstallDispatcher._install_mcp``）连接、
把远端工具注册进本地工具集。

端点注册表是**运行期状态**、不是配置项：它由 ``mcp add`` 写入、带连接句柄语义，
不进 ``ConfigSpec``（端点名是开放集合，同 ``features.<模块>`` 之于 ``GATABLE_MODULES``）。

文件损坏或条目残缺 → ``warnings.warn`` **降级跳过**（同 change 0064 的告警口径）：
不静默丢弃配置，也不阻断启动。

对应接口：doc/03-interfaces/mcp-interface.md §7
"""

from __future__ import annotations

import json
import os
import shlex
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from core.plugin_registry import InstallableAsset, PluginKind, PluginSource

from .errors import MCPError, MCPErrorCode

_STATE_FILE = "mcp-endpoints.json"
_VERSION = 1
_URL_PREFIXES = ("http://", "https://")


def mcp_endpoints_path() -> Path:
    """端点注册表路径：``$CORE_STATE_DIR``（缺省 ``~/.core/state``）/mcp-endpoints.json。"""
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / _STATE_FILE


def default_endpoint_name(source: str, command: str | None = None) -> str:
    """缺省端点名：URL → 主机名（含端口），命令行 → 命令基名（``--name`` 可覆盖）。"""
    raw = (command or source).strip()
    if raw.startswith(_URL_PREFIXES):
        return urlparse(raw).hostname or raw
    tokens = shlex.split(raw)
    return Path(tokens[0]).name if tokens else ""


@dataclass(frozen=True)
class EndpointRecord:
    """已安装端点记录：安装名 + 原始来源 + 形状覆盖（可 JSON 往返）。"""

    name: str
    source: str
    transport: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list[str])

    def manifest(self) -> dict[str, Any]:
        """转安装管线 manifest（``InstallDispatcher._install_mcp`` 的消费口径，单一解析点）。"""
        manifest: dict[str, Any] = {"name": self.name, "endpoint": self.source}
        if self.transport:
            manifest["transport"] = self.transport
        if self.command:
            manifest["command"] = self.command
        if self.args:
            manifest["args"] = list(self.args)
        return manifest

    def asset(self) -> InstallableAsset:
        """端点记录即安装资产（来源固定 mcp-endpoint）—— 安装与卸载两处共用同一构造。"""
        return InstallableAsset(
            kind=PluginKind.MCP, source=PluginSource.MCP_ENDPOINT, manifest=self.manifest()
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
        }

    @classmethod
    def from_json(cls, raw: Any) -> EndpointRecord:
        """反序列化；缺 name / source 视为**残缺条目**（由调用方告警跳过）。"""
        if not isinstance(raw, dict):
            # 调用方（_records）只捕 ValueError；类型不符与字段残缺同路处理，故不换 TypeError。
            raise ValueError("条目不是映射")  # noqa: TRY004
        entry = cast("dict[str, Any]", raw)
        name = str(entry.get("name") or "")
        source = str(entry.get("source") or "")
        if not name or not source:
            raise ValueError("条目缺少 name / source")  # noqa: TRY003 — 残缺说明进告警
        raw_args = entry.get("args")
        args = (
            [str(item) for item in cast("list[Any]", raw_args)]
            if isinstance(raw_args, list)
            else []
        )
        transport = entry.get("transport")
        command = entry.get("command")
        return cls(
            name=name,
            source=source,
            transport=str(transport) if transport else None,
            command=str(command) if command else None,
            args=args,
        )


class MCPEndpointRegistry:
    """已安装 MCP 端点的跨进程注册表（单文件 JSON）。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def list(self) -> list[EndpointRecord]:
        """全部已装端点（按名排序，读盘即最新 —— 跨进程写入彼此可见）。"""
        records = self._records()
        return [records[name] for name in sorted(records)]

    def get(self, name: str) -> EndpointRecord | None:
        return self._records().get(name)

    def add(self, record: EndpointRecord) -> None:
        """登记端点；**同名拒绝**（静默覆盖会丢掉另一个端点的配置）。"""
        records = self._records()
        if record.name in records:
            raise MCPError(
                MCPErrorCode.ENDPOINT_NAME_CONFLICT,
                f"端点名已存在: {record.name}（先 mcp remove，或用 --name 换名）",
            )
        records[record.name] = record
        self._write(records)

    def remove(self, name: str) -> bool:
        """摘除端点；返回是否确有该条目（未安装时 False，由调用方决策）。"""
        records = self._records()
        if name not in records:
            return False
        del records[name]
        self._write(records)
        return True

    def _records(self) -> dict[str, EndpointRecord]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.warn(f"MCP 端点注册表不可读，已忽略: {self._path}（{exc}）", stacklevel=2)
            return {}
        entries: Any = (
            cast("dict[str, Any]", raw).get("endpoints") if isinstance(raw, dict) else None
        )
        if not isinstance(entries, dict):
            warnings.warn(f"MCP 端点注册表格式非法，已忽略: {self._path}", stacklevel=2)
            return {}
        records: dict[str, EndpointRecord] = {}
        for key, entry in cast("dict[str, Any]", entries).items():
            try:
                record = EndpointRecord.from_json(entry)
            except ValueError as exc:
                warnings.warn(f"MCP 端点条目残缺，已跳过: {key}（{exc}）", stacklevel=2)
                continue
            records[record.name] = record
        return records

    def _write(self, records: dict[str, EndpointRecord]) -> None:
        """原子写：tmp + ``os.replace``（中途失败不得损坏既有注册表）。"""
        payload = {
            "version": _VERSION,
            "endpoints": {name: records[name].to_json() for name in sorted(records)},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._path)
