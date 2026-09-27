"""CLI 运维命令面（横切 cli-ops）。

统一 CLI 命令集（六组）+ 启动参数映射（ConfigSpec 单一真源驱动 CLI flag /
env / config.yaml 三层一一对应，优先级链 CLI flag > env > config.yaml > 默认值）。

对应规格：doc/openspec/specs/cli-ops/spec.md
接口：doc/03-interfaces/cli-ops-interface.md
"""

from .dispatcher import CLICommandDispatcher
from .errors import CliOpsError, CliOpsErrorCode
from .models import CommandGroup
from .param_mapper import ParamMapper

__all__ = [
    "CLICommandDispatcher",
    "CliOpsError",
    "CliOpsErrorCode",
    "CommandGroup",
    "ParamMapper",
]
