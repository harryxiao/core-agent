"""列表视图：会话 / 配置 / MCP 端点 / 技能 / 笔记（**只读**，与 `doctor` / `status` 同源同形状）。

红线（写进规格与测试）：**输出不含密钥值** —— 配置视图只出 `${VAR}` 引用名与「可解析」结论；
MCP 视图**不出** `EndpointRecord.args`（其可能是 `--token <值>` 形态）。

对应规格：doc/openspec/specs/cli-ops/spec.md「自检诊断（doctor）与运行状态（status）」
对应接口：doc/03-interfaces/cli-ops-interface.md §5
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

from core.diagnostics.deps import Deps
from core.diagnostics.models import Report
from core.skillhub import MarketIndex, SkillHubError

_NOT_WIRED = "未接线（句柄未注入）"
_EMPTY = "（空）"


def render_sessions(deps: Deps) -> Report:
    """会话清单（id / 标题 / 更新时间）：取**注入**句柄（诊断包不引 `core.ui`）。"""
    handle = deps.sessions
    if handle is None:
        return Report(title="会话", lines=(_NOT_WIRED,))

    def rows() -> list[str]:
        return [
            f"{entry.get('session_id', '')}\t{entry.get('title') or '（无标题）'}"
            f"\t{_as_int(entry.get('updated_at'))}"
            for entry in handle()
        ]

    return _sealed("会话", rows)


def render_config(deps: Deps) -> Report:
    """有效配置摘要：非密钥项照出；密钥项**只出 `${VAR}` 引用名 + 可解析结论**。"""
    manager = deps.config
    if manager is None:
        return Report(title="配置", lines=(_NOT_WIRED,))
    try:
        app = manager.load()
    except Exception as exc:  # noqa: BLE001 — 配置坏了正是要看到的结论
        return Report(title="配置", lines=(f"配置不可用：{type(exc).__name__}: {exc}",))
    rounds, tokens = manager.loop_limits()
    resolvable = "可解析" if manager.is_resolvable(app.llm.api_key_ref) else "不可解析"
    lines = [
        f"provider\t{app.llm.provider}",
        f"model\t{app.llm.model}",
        f"endpoint\t{app.llm.endpoint}",
        f"密钥引用\t{app.llm.api_key_ref}\t{resolvable}",
        f"权限模式\t{manager.permission_mode()}",
        f"循环预算\tmax_rounds={rounds}, token_budget={tokens}",
    ]
    if app.features:
        flags = ", ".join(
            f"{name}={'on' if on else 'off'}" for name, on in sorted(app.features.items())
        )
        lines.append(f"功能开关\t{flags}")
    return Report(title="配置", lines=tuple(lines))


def render_mcp(deps: Deps) -> Report:
    """MCP 端点清单（名 / 传输 / 来源）：**不出 `args`**（可能含 `--token` 形态）。"""
    registry = deps.mcp
    if registry is None:
        return Report(title="MCP 端点", lines=(_NOT_WIRED,))
    return _sealed(
        "MCP 端点",
        lambda: [
            f"{record.name}\t{record.transport or '自动'}\t{record.source}"
            for record in registry.list()
        ],
    )


def render_skills(deps: Deps) -> Report:
    """技能清单：**已装**（技能库）+ **目录**（市场落盘态）。"""
    lines: list[str] = []
    library = deps.library
    if library is not None:
        skills = sorted(library.all_skills(), key=lambda skill: skill.skill_id)
        lines.append(f"已装技能库\t{len(skills)}")
        lines.extend(f"· {skill.skill_id}（{skill.status}, {skill.version}）" for skill in skills)
    market = deps.market
    if market is not None:
        lines.extend(_catalog_lines(market))
    return Report(title="技能", lines=tuple(lines) if lines else (_NOT_WIRED,))


def _catalog_lines(market: MarketIndex) -> list[str]:
    """市场目录行：源未建立（空目录）或不可用 ⇒ 只省掉目录段（不阻断已装技能呈现）。"""
    try:
        catalog = market.list()
    except SkillHubError:
        return []
    rows = [f"市场目录\t{len(catalog)}"] if catalog else []
    rows.extend(f"· {item.skill_id}（{item.status}, {item.version}）" for item in catalog)
    return rows


def render_notes(deps: Deps) -> Report:
    """canonical 笔记清单：等宽列（**按显示宽度**补齐）+ `[常驻 优先 N]` 标记常驻项。"""
    store = deps.notes
    if store is None:
        return Report(title="笔记", lines=(_NOT_WIRED,))

    def rows() -> list[str]:
        notes = store.list()
        if not notes:
            return []
        w_id = max(_display_width(n.note_id) for n in notes)
        w_title = max(_display_width(n.title or n.note_id) for n in notes)
        return [
            f"{_pad(n.note_id, w_id)}  {_pad(n.title or n.note_id, w_title)}  {int(n.updated_at)}"
            f"{f' [常驻 优先 {n.pin_priority}]' if n.pinned else ''}"
            for n in notes
        ]

    return _sealed("笔记", rows)


def _display_width(text: str) -> int:
    """文本的**显示列宽**：东亚宽 / 全角字符按 2 列计，其余按 1 列。

    `len()` 是**字符数**，与终端等宽字体下的列数不等 —— 含中日韩字符的清单若按字符数补齐，
    列起点仍随内容错位（一条中文标题会把后列整体推右）。
    """
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def _pad(text: str, width: int) -> str:
    """按**显示宽度**左对齐补齐到 `width` 列（`f"{text:<{width}}"` 只数字符数）。"""
    return text + " " * max(0, width - _display_width(text))


def _as_int(value: object) -> int:
    """数值字段容错取值（诊断视图不因脏数据崩）。"""
    try:
        return int(float(str(value)))
    except ValueError:
        return 0


def _sealed(title: str, reader: Callable[[], list[str]]) -> Report:
    """只读列表渲染：空 ⇒ `（空）`；读取异常 ⇒ 一行说明（视图不抛）。"""
    try:
        rows = reader()
    except Exception as exc:  # noqa: BLE001 — 视图降级成一行说明，不抛
        return Report(title=title, lines=(f"不可读（{type(exc).__name__}）",))
    return Report(title=title, lines=tuple(rows) if rows else (_EMPTY,))
