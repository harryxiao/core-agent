"""诊断数据模型（**纯数据 + 纯渲染**，无副作用）。

`Check` / `Report` 是 `doctor` / `status` / 各列表视图的**唯一**产出形状：CLI 打印它，
TUI（change 0162）同格式复用（ADR-0153 决策③「单一产出、多消费面」）。

对应接口：doc/03-interfaces/cli-ops-interface.md §5
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CheckStatus(StrEnum):
    """单项检查结论（三档）：`fail` 是**判据**（非零退出），`warn` 仅提示。"""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


_MARKS: dict[CheckStatus, str] = {
    CheckStatus.OK: "✓",
    CheckStatus.WARN: "!",
    CheckStatus.FAIL: "✗",
}


@dataclass(frozen=True)
class Check:
    """单项诊断结论：`name` 是人读短名，`detail` 是**不含密钥值**的补充说明。"""

    name: str
    status: CheckStatus
    detail: str = ""


@dataclass(frozen=True)
class Report:
    """诊断报告：`checks` 为逐项结论（doctor），`lines` 为自由文本行（status / 列表视图）。"""

    title: str
    checks: tuple[Check, ...] = ()
    lines: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """无 `fail` 项即为真（`warn` 不阻断 —— 告警是提示面，不是判据）。"""
        return all(check.status is not CheckStatus.FAIL for check in self.checks)


def render(report: Report) -> list[str]:
    """渲染为可打印行：标题 → 逐项（状态字形 + 明细）→ 自由行（缩进两级）。"""
    rows = [report.title]
    for check in report.checks:
        tail = f" —— {check.detail}" if check.detail else ""
        rows.append(f"  {_MARKS[check.status]} {check.name}{tail}")
    rows.extend(f"  {line}" for line in report.lines)
    return rows
