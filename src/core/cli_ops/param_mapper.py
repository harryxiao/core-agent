"""启动参数映射（ParamMapper）。

以 ConfigSpec 为单一真源，建立 CLI flag / env / config.yaml 三层参数一一
对应（优先级链 CLI flag > env > config.yaml > 默认值），暴露面按
core/advanced/hidden 分级。

对应接口：doc/03-interfaces/cli-ops-interface.md §3
"""

from __future__ import annotations

from typing import Any

from core.configuration import ConfigExposure, ConfigSpec, config_specs, resolve


class ParamMapper:
    """参数映射：消费 ConfigSpec 单一真源，三层优先级解析 + 三面生成。"""

    def __init__(self, *, specs: list[ConfigSpec] | None = None) -> None:
        self._specs = list(specs) if specs is not None else list(config_specs())

    def resolve(
        self,
        key: str,
        *,
        cli: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
        yaml: dict[str, Any] | None = None,
    ) -> Any:
        """按优先级链 CLI flag > env > config.yaml > 默认值 解析配置项。"""
        return resolve(key, cli=cli, env=env, yaml=yaml, specs=self._specs)

    def generate_cli(self, *, include_hidden: bool = False) -> list[str]:
        """由 ConfigSpec 生成 CLI 参数面（含 core/advanced/hidden 分级）。"""
        flags: list[str] = []
        for spec in self._specs:
            if spec.exposure is ConfigExposure.HIDDEN and not include_hidden:
                continue
            flags.append(spec.cli_flag)
        return flags

    def generate_env(self) -> dict[str, str]:
        """由 ConfigSpec 生成 env 变量面（env_var → 默认值）。"""
        return {
            spec.env_var: str(spec.default) if spec.default is not None else ""
            for spec in self._specs
        }

    def generate_yaml_schema(self) -> dict[str, Any]:
        """由 ConfigSpec 生成 yaml schema（map_to → 默认值）。"""
        return {spec.map_to: spec.default for spec in self._specs}
