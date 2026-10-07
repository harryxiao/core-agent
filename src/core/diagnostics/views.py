"""列表视图：会话 / 配置 / MCP 端点 / 技能 / 笔记（**只读**，与 `doctor` / `status` 同源同形状）。

红线（写进规格与测试）：**输出不含密钥值** —— 配置视图只出 `${VAR}` 引用名与「可解析」结论；
MCP 视图**不出** `EndpointRecord.args`（其可能是 `--token <值>` 形态）。

列对齐一律经 `core.diagnostics.align`（**单一实现**）：表格型 `align_rows` / 键值型 `align_pairs`。

对应规格：doc/openspec/specs/cli-ops/spec.md「自检诊断（doctor）与运行状态（status）」「诊断视图列对齐」
对应接口：doc/03-interfaces/cli-ops-interface.md §5
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from core.diagnostics.align import align_pairs, align_rows
from core.diagnostics.deps import Deps
from core.diagnostics.models import Report
from core.skillhub import MarketIndex, MarketSkill, SkillHubError
from core.skills import Skill

_NOT_WIRED = "未接线（句柄未注入）"
_EMPTY = "（空）"


def render_sessions(deps: Deps) -> Report:
    """会话清单（id / 标题 / 更新时间）：取**注入**句柄（诊断包不引 `core.ui`）。"""
    handle = deps.sessions
    if handle is None:
        return Report(title="会话", lines=(_NOT_WIRED,))

    def rows() -> list[str]:
        return align_rows(
            [
                [
                    str(entry.get("session_id", "")),
                    str(entry.get("title") or "（无标题）"),
                    str(_as_int(entry.get("updated_at"))),
                ]
                for entry in handle()
            ]
        )

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
    entries: list[tuple[str, str] | str] = [
        ("provider", app.llm.provider),
        ("model", app.llm.model),
        ("endpoint", app.llm.endpoint),
        ("密钥引用", f"{app.llm.api_key_ref}{'  '}{resolvable}"),
        ("权限模式", manager.permission_mode()),
        ("循环预算", f"max_rounds={rounds}, token_budget={tokens}"),
    ]
    if app.features:
        flags = ", ".join(
            f"{name}={'on' if on else 'off'}" for name, on in sorted(app.features.items())
        )
        entries.append(("功能开关", flags))
    return Report(title="配置", lines=tuple(align_pairs(entries)))


def render_mcp(deps: Deps) -> Report:
    """MCP 端点清单（名 / 传输 / 来源）：**不出 `args`**（可能含 `--token` 形态）。"""
    registry = deps.mcp
    if registry is None:
        return Report(title="MCP 端点", lines=(_NOT_WIRED,))
    return _sealed(
        "MCP 端点",
        lambda: align_rows(
            [[record.name, record.transport or "自动", record.source] for record in registry.list()]
        ),
    )


def render_skills(deps: Deps) -> Report:
    """技能清单：**已装**（技能库）+ **目录**（市场落盘态）。键值行标签对齐、明细行原样。"""
    entries: list[tuple[str, str] | str] = []
    library = deps.library
    if library is not None:
        skills = sorted(library.all_skills(), key=lambda skill: skill.skill_id)
        entries.append(("已装技能库", str(len(skills))))
        entries.extend(_detail_lines(skills))
    market = deps.market
    if market is not None:
        entries.extend(_catalog_entries(market))
    return Report(title="技能", lines=tuple(align_pairs(entries)) if entries else (_NOT_WIRED,))


def _catalog_entries(market: MarketIndex) -> list[tuple[str, str] | str]:
    """市场目录条目：源未建立（空目录）或不可用 ⇒ 只省掉目录段（不阻断已装技能呈现）。"""
    try:
        catalog = market.list()
    except SkillHubError:
        return []
    rows: list[tuple[str, str] | str] = []
    if catalog:
        rows.append(("市场目录", str(len(catalog))))
    rows.extend(_detail_lines(catalog))
    return rows


def _detail_lines(items: Iterable[Skill | MarketSkill]) -> list[str]:
    """逐条明细行（不参与补齐）：`· <标识>（<状态>, <版本>）`。"""
    return [f"· {item.skill_id}（{item.status}, {item.version}）" for item in items]


def render_notes(deps: Deps) -> Report:
    """canonical 笔记清单：等宽列（**按显示宽度**补齐）+ `[常驻 优先 N]` 标记常驻项。"""
    store = deps.notes
    if store is None:
        return Report(title="笔记", lines=(_NOT_WIRED,))

    def rows() -> list[str]:
        notes = store.list()
        return align_rows(
            [
                [
                    n.note_id,
                    n.title or n.note_id,
                    f"{int(n.updated_at)}{f' [常驻 优先 {n.pin_priority}]' if n.pinned else ''}",
                ]
                for n in notes
            ]
        )

    return _sealed("笔记", rows)


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
