"""运行环境壳方言探测（tools / loop 共用）。

产出 ``EnvironmentSnapshot`` 供系统提示注入与 ``code_run`` 缺省方言解析。
探测为纯函数风格：``system`` / ``which`` 可注入，单测不打真实 PATH。

对应规格：loop「运行环境事实」｜ tool-use「内置原子工具」｜ change 0237
"""

from __future__ import annotations

import platform as _platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

ShellDialect = Literal["powershell", "bash", "unknown"]
PathStyle = Literal["windows", "posix"]

Which = Callable[[str], str | None]
SystemName = Callable[[], str]


@dataclass(frozen=True)
class EnvironmentSnapshot:
    """宿主 OS + 默认壳 + 解释器可得性（注入 planner / code_run）。"""

    os: str
    default_shell: ShellDialect
    shell_label: str
    path_style: PathStyle
    has_pwsh: bool
    has_powershell: bool
    has_bash: bool


def probe_environment(
    *,
    system: SystemName | None = None,
    which: Which | None = None,
) -> EnvironmentSnapshot:
    """探测当前宿主环境；``system`` / ``which`` 缺省用 stdlib。"""
    sys_name = (system or _platform.system)()
    find = which or shutil.which
    has_pwsh = find("pwsh") is not None
    has_powershell = find("powershell") is not None
    has_bash = find("bash") is not None

    if sys_name == "Windows":
        os_label = "Windows"
        default: ShellDialect = "powershell"
        path_style: PathStyle = "windows"
        if has_pwsh:
            label = "pwsh"
        elif has_powershell:
            label = "powershell"
        else:
            label = "powershell (未检测到解释器)"
    elif sys_name == "Darwin":
        os_label = "Darwin"
        default = "bash"
        path_style = "posix"
        label = "bash" if has_bash else "bash (未检测到解释器)"
    elif sys_name == "Linux":
        os_label = "Linux"
        default = "bash"
        path_style = "posix"
        label = "bash" if has_bash else "bash (未检测到解释器)"
    else:
        os_label = sys_name or "Other"
        default = "unknown"
        path_style = "posix"
        label = "unknown"

    return EnvironmentSnapshot(
        os=os_label,
        default_shell=default,
        shell_label=label,
        path_style=path_style,
        has_pwsh=has_pwsh,
        has_powershell=has_powershell,
        has_bash=has_bash,
    )


def format_env_block(snap: EnvironmentSnapshot) -> str:
    """渲染系统提示「运行环境」块正文（不含标题行）。"""
    if snap.path_style == "windows":
        path_hint = "路径可用盘符与 \\ 或 /；勿假设 /usr、/tmp 为 POSIX 根目录。"
        syntax_hint = (
            "默认壳为 PowerShell：避免 bash 独有的 && 链 / export / heredoc；"
            "改用 PowerShell 等价写法或分多次 code_run。"
        )
    else:
        path_hint = "路径使用 POSIX 风格（/ 分隔）。"
        syntax_hint = "默认壳为 bash：使用 POSIX 句法；勿假设 PowerShell cmdlet 可用。"
    return "\n".join(
        [
            f"OS：{snap.os}",
            f"默认 shell：{snap.default_shell}（{snap.shell_label}）",
            path_hint,
            syntax_hint,
            "文件读写优先 file_* 工具；shell（code_run）仅用于确需子进程的操作。",
        ]
    )


def resolve_run_type(type_value: str | None, snap: EnvironmentSnapshot) -> str:
    """解析 code_run 的有效 type：显式非空优先；否则按平台默认壳（unknown → bash）。"""
    if isinstance(type_value, str) and type_value.strip():
        return type_value.strip().lower()
    if snap.default_shell == "powershell":
        return "powershell"
    return "bash"


def shell_argv(type_name: str, script: str, snap: EnvironmentSnapshot) -> list[str]:
    """方言 → 子进程 argv；缺解释器 ⇒ ``ValueError``（由工具层归一结构化错误）。"""
    if type_name == "bash":
        if not snap.has_bash:
            raise ValueError("bash 解释器不可用（PATH 未找到 bash）")  # noqa: TRY003
        return ["bash", "-c", script]
    if type_name == "powershell":
        if snap.has_pwsh:
            exe = "pwsh"
        elif snap.has_powershell:
            exe = "powershell"
        else:
            raise ValueError(  # noqa: TRY003
                "PowerShell 解释器不可用（PATH 未找到 pwsh/powershell）"
            )
        return [exe, "-NoProfile", "-Command", script]
    raise ValueError(f"未知 code_run type: {type_name}")  # noqa: TRY003
