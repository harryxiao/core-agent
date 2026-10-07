"""诊断检查项：逐项只读自检（`doctor`）与运行概览（`status`）。

一切失败都**落成 `Check` / 一行说明**（配置不可读、句柄未注入、注册表损坏）—— 诊断的职责正是
**报告**不可用；若向上抛，"配置坏了"这个最该跑诊断的场景反而看不到诊断。

**只读保证**：不建外部连接（不探端点活性、不调 LLM、不触网）、不写盘（状态目录只**探测**
最近存在的祖先，不创建）、不读密钥值（只经 `ConfigManager.is_resolvable` 取布尔）。

对应规格：doc/openspec/specs/cli-ops/spec.md「自检诊断（doctor）与运行状态（status）」
对应接口：doc/03-interfaces/cli-ops-interface.md §5
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from core.configuration import AppConfig, ConfigManager
from core.diagnostics.deps import Deps
from core.diagnostics.models import Check, CheckStatus, Report

_NOT_WIRED = "未接线（句柄未注入）"
_FALLBACK = "不可读"


# ---- doctor ----


def collect_doctor(deps: Deps) -> Report:
    """逐项自检：配置 / 密钥引用 / 状态目录 / 工具面 / 笔记 / MCP 端点 / 资产账本 / 技能库。"""
    config_check, app = _check_config(deps)
    checks = [config_check]
    if app is not None and deps.config is not None:
        checks.extend(_check_secrets(deps.config, app))
    checks.extend(
        (
            _check_state_dir(deps),
            _check_tools(deps),
            _check_notes(deps),
            _check_mcp(deps),
            _check_assets(deps),
            _check_skills(deps),
        )
    )
    return Report(title="自检诊断（doctor）", checks=tuple(checks))


def _check_config(deps: Deps) -> tuple[Check, AppConfig | None]:
    """配置项：加载 + schema 校验（**复用** `ConfigManager.validate_schema`，不自建第二套）。"""
    manager = deps.config
    if manager is None:
        return Check("配置", CheckStatus.WARN, _NOT_WIRED), None
    try:
        app = manager.load()
    except Exception as exc:  # noqa: BLE001 — 配置坏了正是诊断要报告的事，不向上抛
        return Check("配置", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}"), None
    warnings = manager.validate_schema(app).warnings
    if warnings:
        return Check("配置", CheckStatus.WARN, f"schema 有效（{len(warnings)} 项告警）"), app
    return Check("配置", CheckStatus.OK, "schema 有效"), app


def _check_secrets(manager: ConfigManager, app: AppConfig) -> list[Check]:
    """密钥引用逐条：**只判可解析**（`is_resolvable` 只回布尔），只呈现 `${VAR}` 引用名。

    SHALL NOT 呈现解析结果（红线「密钥只引用不读取、绝不进日志/记忆」在诊断面同样成立）。
    """
    refs: list[tuple[str, str]] = [("密钥引用（LLM）", app.llm.api_key_ref)]
    if app.im is not None:
        refs.append(("密钥引用（IM）", app.im.secret_ref))
    if app.judgment is not None and app.judgment.api_key_ref:
        refs.append(("密钥引用（决策模型）", app.judgment.api_key_ref))
    checks: list[Check] = []
    for name, ref in refs:
        resolvable = manager.is_resolvable(ref)
        checks.append(
            Check(
                name,
                CheckStatus.OK if resolvable else CheckStatus.FAIL,
                f"{ref} {'可解析' if resolvable else '不可解析'}",
            )
        )
    return checks


def _check_state_dir(deps: Deps) -> Check:
    """状态目录可写性：**只读探测**（不存在则探最近存在的祖先，不创建任何目录）。"""
    path = deps.state_dir
    if path is None:
        return Check("状态目录", CheckStatus.WARN, _NOT_WIRED)
    anchor = _existing_anchor(path)
    if not os.access(anchor, os.W_OK):
        return Check("状态目录", CheckStatus.FAIL, f"{anchor} 不可写")
    detail = f"{path} 可写" if anchor == path else f"{path} 不存在（{anchor} 可写 ⇒ 可创建）"
    return Check("状态目录", CheckStatus.OK, detail)


def _existing_anchor(path: Path) -> Path:
    """沿父目录上溯到**已存在**的最近祖先（都不存在则回落自身）。"""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return path


def _check_tools(deps: Deps) -> Check:
    provider = deps.tools
    if provider is None:
        return Check("工具面", CheckStatus.WARN, _NOT_WIRED)
    return _read("工具面", lambda: f"{len(provider.active_tools())} 个工具已注册")


def _check_notes(deps: Deps) -> Check:
    store = deps.notes
    if store is None:
        return Check("笔记（canonical）", CheckStatus.WARN, _NOT_WIRED)
    return _read("笔记（canonical）", lambda: f"{len(store.list())} 篇")


def _check_mcp(deps: Deps) -> Check:
    registry = deps.mcp
    if registry is None:
        return Check("MCP 端点表", CheckStatus.WARN, _NOT_WIRED)
    return _read("MCP 端点表", lambda: f"{len(registry.list())} 个端点")


def _check_assets(deps: Deps) -> Check:
    installer = deps.installer
    if installer is None:
        return Check("资产账本", CheckStatus.WARN, _NOT_WIRED)
    return _read("资产账本", lambda: f"{len(installer.installed())} 项已安装")


def _check_skills(deps: Deps) -> Check:
    library = deps.library
    if library is None:
        return Check("技能库", CheckStatus.WARN, _NOT_WIRED)
    return _read("技能库", lambda: f"{len(library.all_skills())} 个技能")


def _read(label: str, reader: Callable[[], str]) -> Check:
    """执行一次只读读取：成功 ⇒ `ok`（附读数），异常 ⇒ `fail`（附原因，不抛）。"""
    try:
        return Check(label, CheckStatus.OK, reader())
    except Exception as exc:  # noqa: BLE001 — 诊断报告失败，不向上抛
        return Check(label, CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")


# ---- status ----


def collect_status(deps: Deps) -> Report:
    """运行概览（信息面，**非**判据）：恒不产生 `fail` 项 ⇒ 恒退出码 0。

    各字段**独立降级**：某项不可读只令该行如实标注，不影响其余行。
    """
    app, failure = _loaded_config(deps)
    lines = (
        f"模型\t{_model(app, failure)}",
        f"循环预算\t{_budget(app, failure, deps)}",
        f"会话数\t{_field(deps.sessions, lambda handle: str(len(handle())))}",
        f"内置工具\t{_field(deps.tools, lambda provider: str(len(provider.active_tools())))}",
        f"已安装资产\t{_field(deps.installer, lambda inst: str(len(inst.installed())))}",
        f"MCP 端点\t{_field(deps.mcp, lambda reg: str(len(reg.list())))}",
        f"技能库\t{_field(deps.library, lambda lib: str(len(lib.all_skills())))}",
        f"笔记\t{_field(deps.notes, lambda store: str(len(store.list())))}",
    )
    return Report(title="运行状态（status）", lines=lines)


def _loaded_config(deps: Deps) -> tuple[AppConfig | None, str]:
    """加载有效配置：返回 `(AppConfig|None, 失败说明)`；诊断不向上抛配置异常。"""
    manager = deps.config
    if manager is None:
        return None, _NOT_WIRED
    try:
        return manager.load(), ""
    except Exception as exc:  # noqa: BLE001 — 概览如实标注，不因配置坏了整体失败
        return None, f"配置不可用（{type(exc).__name__}）"


def _model(app: AppConfig | None, failure: str) -> str:
    return f"{app.llm.provider} / {app.llm.model}" if app is not None else failure


def _budget(app: AppConfig | None, failure: str, deps: Deps) -> str:
    if app is None or deps.config is None:
        return failure
    rounds, tokens = deps.config.loop_limits()
    return f"max_rounds={rounds}, token_budget={tokens}"


_T = TypeVar("_T")


def _field(handle: _T | None, reader: Callable[[_T], str]) -> str:
    """一行概览值：未注入 ⇒ 如实标注；读取异常 ⇒ `不可读（异常类型）`（只出类型，不出消息）。"""
    if handle is None:
        return _NOT_WIRED
    try:
        return reader(handle)
    except Exception as exc:  # noqa: BLE001 — 概览不因单项不可读而整体失败
        return f"{_FALLBACK}（{type(exc).__name__}）"
