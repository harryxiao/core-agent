"""cli-ops 单元测试（对齐 §27 契约 + M4 验收锚点）。

覆盖：六组命令路由 / 未识别命令拒绝 / 参数映射优先级链 / 暴露面分级。
"""

from __future__ import annotations

import pytest

from core.cli_ops import CLICommandDispatcher, CliOpsError, CliOpsErrorCode, ParamMapper
from core.configuration import ConfigExposure, ConfigSpec


def _mapper_specs() -> list[ConfigSpec]:
    return [
        ConfigSpec("app.name", "--app.name", "CORE_APP_NAME", default="core", map_to="app.name"),
        ConfigSpec(
            "app.secret",
            "--app.secret",
            "CORE_APP_SECRET",
            default="",
            map_to="app.secret",
            exposure=ConfigExposure.HIDDEN,
        ),
    ]


# ---- 命令路由 ----


def test_dispatch_unknown_command_raises() -> None:
    d = CLICommandDispatcher()
    with pytest.raises(CliOpsError) as exc_info:
        d.dispatch(["frobnicate"])
    assert exc_info.value.code is CliOpsErrorCode.UNKNOWN_COMMAND


def test_dispatch_empty_raises() -> None:
    d = CLICommandDispatcher()
    with pytest.raises(CliOpsError) as exc_info:
        d.dispatch([])
    assert exc_info.value.code is CliOpsErrorCode.UNKNOWN_COMMAND


def test_dispatch_groups_covered() -> None:
    d = CLICommandDispatcher()
    assert d.dispatch(["start"]) == 0  # lifecycle
    assert d.dispatch(["status"]) == 0  # status
    assert d.dispatch(["version"]) == 0  # status
    assert d.dispatch(["install"]) == 0  # asset
    assert d.dispatch(["list"]) == 0  # asset
    assert d.dispatch(["mcp", "add", "x"]) == 0  # connection
    assert d.dispatch(["auth"]) == 0  # security
    assert d.dispatch(["permission-mode"]) == 0  # security
    assert d.dispatch(["gateway"]) == 0  # gateway


def test_status_version_and_help() -> None:
    d = CLICommandDispatcher()
    assert d.dispatch(["version"]) == 0
    assert d.dispatch(["help"]) == 0


# ---- 参数映射 ----


def test_resolve_priority_chain() -> None:
    mapper = ParamMapper(specs=_mapper_specs())
    key = "app.name"
    assert mapper.resolve(key) == "core"  # 默认值
    assert mapper.resolve(key, yaml={"app.name": "from-yaml"}) == "from-yaml"
    assert (
        mapper.resolve(key, yaml={"app.name": "from-yaml"}, env={"CORE_APP_NAME": "from-env"})
        == "from-env"
    )
    assert (
        mapper.resolve(
            key,
            cli={"app.name": "from-cli"},
            yaml={"app.name": "from-yaml"},
            env={"CORE_APP_NAME": "from-env"},
        )
        == "from-cli"
    )


def test_generate_cli_hides_hidden() -> None:
    mapper = ParamMapper(specs=_mapper_specs())
    flags = mapper.generate_cli()
    assert "--app.name" in flags
    assert "--app.secret" not in flags  # HIDDEN 默认隐藏
    assert "--app.secret" in mapper.generate_cli(include_hidden=True)


def test_generate_env_and_yaml() -> None:
    mapper = ParamMapper(specs=_mapper_specs())
    env = mapper.generate_env()
    assert env["CORE_APP_NAME"] == "core"
    yaml_schema = mapper.generate_yaml_schema()
    assert yaml_schema["app.name"] == "core"
