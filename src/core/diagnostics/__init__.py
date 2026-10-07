"""只读诊断源（横切）：`doctor` / `status` 与各列表视图的**单一**产出方。

分工（ADR-0153）：本包只**收集并渲染事实**，不装配运行时、不猜路径（全部句柄由调用方
经 `Deps` 注入）、不产生副作用（不建连接、不写盘、不读密钥值）。CLI（`entry`）今天消费它，
TUI（change 0162）复用**同一份**产出 —— SHALL NOT 各写一份检查逻辑。

规格：doc/openspec/specs/cli-ops/spec.md「自检诊断（doctor）与运行状态（status）」
接口：doc/03-interfaces/cli-ops-interface.md §5
"""

from .checks import collect_doctor, collect_status
from .deps import Deps, SessionsHandle
from .models import Check, CheckStatus, Report, render
from .views import (
    render_config,
    render_mcp,
    render_notes,
    render_sessions,
    render_skills,
)

__all__ = [
    "Check",
    "CheckStatus",
    "Deps",
    "Report",
    "SessionsHandle",
    "collect_doctor",
    "collect_status",
    "render",
    "render_config",
    "render_mcp",
    "render_notes",
    "render_sessions",
    "render_skills",
]
