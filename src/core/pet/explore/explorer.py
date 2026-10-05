"""受限探索工具集（pet-explore）。

只读优先、需授权、清单可配置（R11）；实现 core.pet.core.ExplorerLayer 探索工具集层。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（探索工具集层）
"""

from __future__ import annotations

# 默认只读探索工具清单 —— **真实工具 id**（change 0081 / 账本 E25）：原清单
# `file.read`/`memory.read`/`web.search` 与仓库真实 id 不对应（`memory` 也非工具）。
# `available()` 现为组合根**受限 ToolProvider 的白名单真源**（R11）。
_DEFAULT_READONLY_TOOLS = {"tools.file_read"}


class Explorer:
    """受限探索工具集：仅授权只读工具可执行。"""

    def __init__(self, *, allowlist: list[str] | None = None) -> None:
        self._allowlist: set[str] = (
            set(allowlist) if allowlist is not None else _DEFAULT_READONLY_TOOLS
        )

    def available(self) -> list[str]:
        """返回已授权工具清单（排序稳定）。"""
        return sorted(self._allowlist)

    def run(self, tool_id: str) -> str:
        """执行只读探索；未授权工具阻断。"""
        if tool_id not in self._allowlist:
            raise PermissionError(f"未授权探索工具: {tool_id}")  # noqa: TRY003
        return f"[{tool_id}] 只读探索结果（真实工具未接）"
