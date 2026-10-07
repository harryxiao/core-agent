"""诊断依赖注入面：**全部可选句柄**由调用方装配（包内不猜路径、不自建运行时）。

`core.diagnostics` 是**只读诊断源**：
- **不** import `core.runtime` —— 组合根唯一性硬红线
  （`tests/test_architecture.py::test_runtime_is_sole_composition_root`）；
- **不** import `core.ui` —— `ui` 反向引用本包（0162），互相引用即成环；会话枚举因此走
  **注入的可调用**（`SessionsHandle`）而非句柄对象。

缺省即「未接线」：诊断**如实报 `warn`**，而不是崩溃或伪造读数。

对应接口：doc/03-interfaces/cli-ops-interface.md §5
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.configuration import ConfigManager
from core.mcp import MCPEndpointRegistry
from core.notes import NoteStore
from core.plugin_registry import PluginInstaller
from core.skillhub import MarketIndex
from core.skills import SkillLibrary
from core.tools import ToolProvider

#: 会话枚举句柄：返回 `[{session_id, mode, created_at}(+title, updated_at)]`
#: （形状与 `ui.UIAPILayer.list_sessions` 一致 —— 同一份数据，两个消费面）。
SessionsHandle = Callable[[], list[dict[str, object]]]


@dataclass(frozen=True)
class Deps:
    """诊断句柄集（**全部可选**）：调用方注入，诊断包不猜路径、不装配运行时。"""

    config: ConfigManager | None = None  # 配置：**只经 is_resolvable 判可解析**，绝不读值
    tools: ToolProvider | None = None  # 工具面：CLI 注入内置原子工具，TUI 注入 runtime 全量
    sessions: SessionsHandle | None = None  # 会话枚举（可调用 ⇒ 无需引 core.ui）
    notes: NoteStore | None = None  # canonical 笔记库
    mcp: MCPEndpointRegistry | None = None  # 已装 MCP 端点表
    library: SkillLibrary | None = None  # 技能库（已装）
    market: MarketIndex | None = None  # 技能市场目录（发布 / 审核落盘态）
    installer: PluginInstaller | None = None  # 插件/资产安装账本
    state_dir: Path | None = None  # 全局状态目录（可写性探测）
