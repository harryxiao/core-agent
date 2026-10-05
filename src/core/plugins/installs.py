"""插件安装账本与按 kind 路由的单一视图（plugins）。

``plugin install`` / ``tools.install`` 的成果必须活过**一次性 CLI 进程**：账本落
``$CORE_STATE_DIR/plugin-installs.json`` —— 单文件 JSON、**原子写**（tmp + ``os.replace``，
同 change 0062）、损坏与残缺条目 ``warnings.warn`` **降级跳过**（不静默丢弃、不阻断启动），
与 ``skills.json`` / ``mcp-endpoints.json`` 同状态目录约定。

mcp 类资产**不**在本账本二次记账：其持久化真源是 ``mcp-endpoints.json``（change 0074 /
ADR-0071）。``PluginInstallStore`` 按 ``kind`` **路由**到该真源，``records()`` 合并两处构成
「已安装」的**单一视图** —— `list` / `uninstall` / 构造期水合共用它。

对应规格：doc/openspec/specs/plugin-registry/spec.md「插件安装持久化」
接口：doc/03-interfaces/plugin-registry-interface.md §8；ADR-0102
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from core.mcp.endpoints import EndpointRecord, MCPEndpointRegistry, mcp_endpoints_path
from core.plugin_registry import InstallableAsset, PluginKind, PluginSource

_STATE_FILE = "plugin-installs.json"
_VERSION = 1


def plugin_installs_path() -> Path:
    """账本路径：``$CORE_STATE_DIR``（缺省 ``~/.core/state``）/plugin-installs.json。"""
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    return base / _STATE_FILE


@dataclass(frozen=True)
class InstallRecord:
    """账本行：plugin_id + 重建物化所需的 kind / source / manifest（可 JSON 往返）。"""

    plugin_id: str
    kind: PluginKind
    source: PluginSource
    manifest: dict[str, Any] = field(default_factory=dict[str, Any])

    def asset(self) -> InstallableAsset:
        """重建安装资产（装配期重建与卸载两处共用同一构造）。"""
        return InstallableAsset(kind=self.kind, source=self.source, manifest=dict(self.manifest))

    def to_json(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "kind": self.kind.value,
            "source": self.source.value,
            "manifest": self.manifest,
        }

    @classmethod
    def from_json(cls, raw: Any) -> InstallRecord:
        """反序列化；缺 plugin_id / kind / source 或取值非法视为**残缺条目**（调用方告警跳过）。"""
        if not isinstance(raw, dict):
            # 调用方（_records）只捕 ValueError；类型不符与字段残缺同路处理，故不换 TypeError。
            raise ValueError("条目不是映射")  # noqa: TRY004
        entry = cast("dict[str, Any]", raw)
        plugin_id = str(entry.get("plugin_id") or "")
        if not plugin_id:
            raise ValueError("条目缺少 plugin_id")  # noqa: TRY003 — 残缺说明进告警
        manifest = entry.get("manifest")
        return cls(
            plugin_id=plugin_id,
            # 取值非法（非四类来源 / 非三类 kind）由枚举自身抛 ValueError，同路降级。
            kind=PluginKind(str(entry.get("kind") or "")),
            source=PluginSource(str(entry.get("source") or "")),
            manifest=dict(cast("dict[str, Any]", manifest)) if isinstance(manifest, dict) else {},
        )


class PluginInstallRegistry:
    """已安装资产的跨进程账本（单文件 JSON；mcp 类不入此表，见 ``PluginInstallStore``）。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def list(self) -> list[InstallRecord]:
        """全部账本条目（按 plugin_id 排序，读盘即最新 —— 跨进程写入彼此可见）。"""
        records = self._records()
        return [records[plugin_id] for plugin_id in sorted(records)]

    def get(self, plugin_id: str) -> InstallRecord | None:
        return self._records().get(plugin_id)

    def put(self, record: InstallRecord) -> None:
        """登记；**同 id 覆盖**（重装即升级）—— 与端点注册表 ``add`` 的重名拒绝语义不同：
        安装动作本身就是 `plugin_id` 的权威来源，无「静默覆盖会丢另一个配置」之虞（ADR-0102）。"""
        records = self._records()
        records[record.plugin_id] = record
        self._write(records)

    def remove(self, plugin_id: str) -> bool:
        """清除条目；返回是否确有该条目（未安装时 False，由调用方决策）。"""
        records = self._records()
        if plugin_id not in records:
            return False
        del records[plugin_id]
        self._write(records)
        return True

    def _records(self) -> dict[str, InstallRecord]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.warn(f"插件安装账本不可读，已忽略: {self._path}（{exc}）", stacklevel=2)
            return {}
        entries: Any = (
            cast("dict[str, Any]", raw).get("installs") if isinstance(raw, dict) else None
        )
        if not isinstance(entries, dict):
            warnings.warn(f"插件安装账本格式非法，已忽略: {self._path}", stacklevel=2)
            return {}
        records: dict[str, InstallRecord] = {}
        for key, entry in cast("dict[str, Any]", entries).items():
            try:
                record = InstallRecord.from_json(entry)
            except ValueError as exc:
                warnings.warn(f"插件安装条目残缺，已跳过: {key}（{exc}）", stacklevel=2)
                continue
            records[record.plugin_id] = record
        return records

    def _write(self, records: dict[str, InstallRecord]) -> None:
        """原子写：tmp + ``os.replace``（中途失败不得损坏既有账本）。"""
        payload = {
            "version": _VERSION,
            "installs": {pid: records[pid].to_json() for pid in sorted(records)},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._path)


class PluginInstallStore:
    """按 ``kind`` 路由的安装视图：mcp → 端点注册表，其余 → 本账本。

    ``records()`` 合并两处 ⇒ `list` / `uninstall` / 构造期水合共用**一份真源**；
    同一资产**不两处记账**（mcp 记录只写端点注册表）。
    """

    def __init__(self, ledger: PluginInstallRegistry, endpoints: MCPEndpointRegistry) -> None:
        self._ledger = ledger
        self._endpoints = endpoints

    def records(self) -> dict[str, InstallableAsset]:
        """全部已安装资产（键为 plugin_id / 端点名，按 kind 取自各自真源）。"""
        merged = {record.plugin_id: record.asset() for record in self._ledger.list()}
        merged.update({record.name: record.asset() for record in self._endpoints.list()})
        return merged

    def put(self, plugin_id: str, asset: InstallableAsset) -> None:
        if asset.kind is PluginKind.MCP:
            record = EndpointRecord.from_manifest(asset.manifest)
            # 端点名缺省取 manifest.name；无 name 时回落 plugin_id，不留无名记录。
            self._endpoints.put(record if record.name else replace(record, name=plugin_id))
            return
        self._ledger.put(
            InstallRecord(
                plugin_id=plugin_id,
                kind=asset.kind,
                source=asset.source,
                manifest=dict(asset.manifest),
            )
        )

    def remove(self, plugin_id: str) -> bool:
        """清除安装记录（先账本后端点表：两处各自判存在，退化为幂等）。"""
        if self._ledger.remove(plugin_id):
            return True
        return self._endpoints.remove(plugin_id)


def default_install_store() -> PluginInstallStore:
    """缺省安装视图：状态目录下的账本 + MCP 端点注册表（CLI 与组合根同一构造）。"""
    return PluginInstallStore(
        PluginInstallRegistry(plugin_installs_path()),
        MCPEndpointRegistry(mcp_endpoints_path()),
    )
