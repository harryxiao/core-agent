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
            label = "PowerShell 7+ (pwsh)"
        elif has_powershell:
            label = "Windows PowerShell 5.1 (powershell)"
        else:
            label = "powershell（未检测到解释器）"
    elif sys_name == "Darwin":
        os_label = "Darwin"
        default = "bash"
        path_style = "posix"
        label = "bash" if has_bash else "bash（未检测到解释器）"
    elif sys_name == "Linux":
        os_label = "Linux"
        default = "bash"
        path_style = "posix"
        label = "bash" if has_bash else "bash（未检测到解释器）"
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


def _available_shells(snap: EnvironmentSnapshot) -> list[str]:
    """PATH 上实际可用的壳（按 pwsh / powershell / bash 顺序）。"""
    candidates = (
        ("pwsh", snap.has_pwsh),
        ("powershell", snap.has_powershell),
        ("bash", snap.has_bash),
    )
    return [name for name, available in candidates if available]


def _default_shell_available(snap: EnvironmentSnapshot) -> bool:
    """默认方言是否有可执行解释器。"""
    if snap.default_shell == "powershell":
        return snap.has_pwsh or snap.has_powershell
    if snap.default_shell == "bash":
        return snap.has_bash
    return False


def format_env_block(snap: EnvironmentSnapshot) -> str:
    """渲染系统提示「运行环境」块正文（不含标题行）。"""
    available = _available_shells(snap)
    lines = [
        f"OS：{snap.os}",
        f"默认 shell：{snap.default_shell}（{snap.shell_label}）",
        "可用 shell："
        + ("、".join(available) if available else "未检测到 bash / pwsh / powershell"),
    ]
    if snap.path_style == "windows":
        lines.append("路径可用盘符与 \\ 或 /；勿假设 /usr、/tmp 为 POSIX 根目录。")
        lines.append(
            "默认壳为 PowerShell：避免 bash 独有的 && 链 / export / heredoc；"
            "改用 PowerShell 等价写法或分多次 code_run。"
        )
    elif snap.default_shell == "bash":
        lines.append("路径使用 POSIX 风格（/ 分隔）。")
        lines.append("默认壳为 bash：使用 POSIX 句法；勿假设 PowerShell cmdlet 可用。")
    else:
        lines.append("路径风格未知：优先用 pathlib 拼接路径，勿硬编码 /tmp 或 /usr。")
        lines.append(
            "默认 shell 未知：执行前显式指定 type（bash / powershell / python），"
            "不确定时用 type=python。"
        )
    if not _default_shell_available(snap):
        lines.append("默认 shell 不可用：改用 type=python（当前解释器始终可用）。")
    lines.append(
        "每次 code_run 都是全新进程：cd 与环境变量不跨调用保留；"
        "需要目录时用 cwd（绝对路径，支持 ~）。"
    )
    lines.append(
        "Python 回退规则：仅在方言不可用或脚本无法用该方言表达时改用 type=python；"
        "优先 pathlib / tempfile 等标准库，勿硬编码 /tmp；勿用回退掩盖方言错误。"
    )
    lines.append("文件读写优先 file_* 工具；shell（code_run）仅用于确需子进程的操作。")
    return "\n".join(lines)


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
