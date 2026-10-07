"""诊断源单元测试（change 0162：`doctor` / `status` 真诊断）。

对齐规格 `cli-ops`「自检诊断（`doctor`）与运行状态（`status`）」四场景，另加两条**红线**守护：

- **密钥零泄漏**：诊断输出逐字不含注入的密钥值，`/mcp` 视图逐字不含端点 `args`（可能含 `--token`）。
- **包边界**：`core.diagnostics` **不** import `core.runtime` / `core.ui`（前者是组合根硬红线，
  后者与本包互相引用会成环 —— `ui` 反向引用诊断源）。
"""

from __future__ import annotations

import ast
import os
import pathlib
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.diagnostics import (
    Check,
    CheckStatus,
    Deps,
    Report,
    collect_doctor,
    collect_status,
    render,
    render_config,
    render_mcp,
    render_notes,
    render_sessions,
    render_skills,
)
from core.mcp import EndpointRecord, MCPEndpointRegistry
from core.notes import NoteStore
from core.skills import Skill, SkillLibrary
from core.tools import ToolProvider, builtin_tools

# 独特标记值：任何输出命中它即判定「密钥泄漏」（可 grep 的哨兵）。
_CANARY = "sk-DIAG-CANARY-9f3a"

_VALID_YAML = """\
llm:
  provider: deepseek
  model: deepseek-chat
  endpoint: https://api.deepseek.com/v1
  api_key: ${CORE_DIAG_KEY}
"""


def _config(
    tmp_path, yaml: str = _VALID_YAML, *, environ: dict[str, str] | None = None
) -> ConfigManager:
    """配置管理器：缺省 env 里**有**可解析的密钥引用（传 ``environ={}`` 造不可解析）。"""
    # 文件名按内容派生：同一 tmp_path 下多次构造互不覆盖（`ConfigManager` 在 `load()` 时才读盘）
    path = tmp_path / f"config-{abs(hash(yaml)):x}.yaml"
    path.write_text(yaml, encoding="utf-8")
    return ConfigManager(path, environ={"CORE_DIAG_KEY": _CANARY} if environ is None else environ)


def _tools() -> ToolProvider:
    provider = ToolProvider()
    for tool in builtin_tools():
        provider.register(tool)
    return provider


def _deps(tmp_path, **overrides: Any) -> Deps:
    """全绿依赖：可解析引用 + 可写状态目录 + 可读注册表（全部落在 tmp_path）。"""
    fields: dict[str, Any] = {
        "config": _config(tmp_path),
        "tools": _tools(),
        "sessions": lambda: [{"session_id": "s1", "mode": "cli"}],
        "notes": NoteStore(path=tmp_path / "notes"),
        "mcp": MCPEndpointRegistry(tmp_path / "mcp.json"),
        "library": SkillLibrary(tmp_path / "skills.json"),
        "state_dir": tmp_path,
        **overrides,
    }
    return Deps(**fields)


def _lines(report: Report) -> str:
    return "\n".join(render(report))


def _all_views(deps: Deps) -> str:
    """doctor / status / 五张列表视图的**全部**输出（泄漏断言用一份文本）。"""
    parts = [_lines(collect_doctor(deps)), _lines(collect_status(deps))]
    views = (render_sessions, render_config, render_mcp, render_skills, render_notes)
    parts.extend(_lines(view(deps)) for view in views)
    return "\n".join(parts)


# ---- 模型与渲染 ----


def test_report_ok_is_no_fail() -> None:
    """无 `fail` 项即真：`warn` 不阻断（告警是提示面）。"""
    assert Report(title="t").ok is True
    warns = Report(title="t", checks=(Check("a", CheckStatus.WARN, "x"),))
    assert warns.ok is True
    assert Report(title="t", checks=(Check("a", CheckStatus.FAIL, "x"),)).ok is False


def test_render_marks_and_detail() -> None:
    """渲染：标题 + 逐项状态字形 + 明细（无明细不带分隔符）。"""
    report = Report(
        title="自检",
        checks=(Check("配置", CheckStatus.OK), Check("密钥", CheckStatus.FAIL, "${K} 不可解析")),
        lines=("自由行",),
    )
    out = render(report)
    assert out[0] == "自检"
    assert out[1].strip().startswith("✓") and "配置" in out[1]
    assert "✗" in out[2] and "${K} 不可解析" in out[2]
    assert out[3].strip() == "自由行"


# ---- doctor ----


def test_doctor_all_green(tmp_path) -> None:
    """场景「自检全绿」：配置有效 + 引用可解析 + 目录可写 + 注册表可读 ⇒ 无 fail。"""
    report = collect_doctor(_deps(tmp_path))
    assert report.ok is True
    assert [c.status for c in report.checks if c.status is CheckStatus.FAIL] == []
    names = " ".join(c.name for c in report.checks)
    for expected in ("配置", "密钥", "状态目录", "工具", "笔记", "MCP", "资产", "技能"):
        assert expected in names


def test_doctor_unresolvable_ref_fails_without_raising(tmp_path) -> None:
    """场景「存在失败项时非零退出」的纯函数面：引用不可解析 ⇒ fail（**不抛**），且逐条列明。"""
    deps = _deps(tmp_path, config=_config(tmp_path, environ={}))
    report = collect_doctor(deps)
    assert report.ok is False
    config_check = next(c for c in report.checks if c.name.startswith("配置"))
    assert config_check.status is CheckStatus.FAIL
    assert "llm.api_key" in config_check.detail  # 写明**哪一项**不可用（配置键名，非取值）
    assert _CANARY not in config_check.detail  # 不呈现取值
    assert len(report.checks) > 1  # 其余项未被吞掉


def test_doctor_missing_config_is_a_fail_not_a_crash(tmp_path) -> None:
    """配置缺失 ⇒ 落成一条 fail 项（诊断的职责是**报告**不可用，不向上抛）。"""
    deps = _deps(tmp_path, config=_config(tmp_path, "llm:\n  provider: deepseek\n"))
    report = collect_doctor(deps)
    assert report.ok is False
    config_check = next(c for c in report.checks if c.name.startswith("配置"))
    assert config_check.status is CheckStatus.FAIL
    assert config_check.detail  # 原因非空（供人定位）


def test_doctor_warns_on_missing_handles(tmp_path) -> None:
    """句柄未注入 ⇒ `warn`（不是 fail）：能力面缺失不等于系统不可用。"""
    report = collect_doctor(Deps(config=_config(tmp_path)))
    statuses = {c.name: c.status for c in report.checks}
    assert all(s is not CheckStatus.FAIL for s in statuses.values())
    assert CheckStatus.WARN in statuses.values()


def test_doctor_unwritable_state_dir_fails(tmp_path) -> None:
    """状态目录不可写 ⇒ fail（且**只读探测**：探测本身不创建目录）。"""
    if os.geteuid() == 0:  # pragma: no cover — root 无视权限位，W_OK 恒真
        pytest.skip("root 下权限位不生效")
    target = tmp_path / "ro"
    target.mkdir()
    target.chmod(0o500)
    try:
        report = collect_doctor(_deps(tmp_path, state_dir=target))
    finally:
        target.chmod(0o700)
    check = next(c for c in report.checks if c.name == "状态目录")
    assert check.status is CheckStatus.FAIL


def test_doctor_reports_secret_ref_name_only(tmp_path) -> None:
    """场景「诊断输出不含密钥值」：只呈现 `${VAR}` 引用名与结论。"""
    out = _lines(collect_doctor(_deps(tmp_path)))
    assert "${CORE_DIAG_KEY}" in out
    assert _CANARY not in out


# ---- status ----


def test_status_overview_fields(tmp_path) -> None:
    """场景「运行状态概览」：六项字段齐备。"""
    deps = _deps(tmp_path)
    text = _lines(collect_status(deps))
    for label in ("会话数", "内置工具", "已安装资产", "MCP 端点", "模型", "循环预算"):
        assert label in text
    assert "deepseek-chat" in text
    assert collect_status(deps).ok is True


def test_status_survives_broken_config(tmp_path) -> None:
    """配置不可用 ⇒ 概览照常出（该项如实标注），不抛。"""
    deps = _deps(tmp_path, config=_config(tmp_path, "llm:\n  provider: deepseek\n"))
    text = _lines(collect_status(deps))
    assert "会话数" in text
    assert _CANARY not in text


def test_status_never_leaks_secret(tmp_path) -> None:
    deps = _deps(tmp_path)
    assert _CANARY not in _all_views(deps)


# ---- 列表视图 ----


def test_render_sessions_uses_injected_handle(tmp_path) -> None:
    """会话视图取**注入**句柄（诊断包不猜路径、不引 `core.ui`）。"""
    out = _lines(render_sessions(_deps(tmp_path)))
    assert "s1" in out


def test_render_mcp_omits_args(tmp_path) -> None:
    """MCP 视图**不出** `args`（其可能是 `--token <值>` 形态）。"""
    registry = MCPEndpointRegistry(tmp_path / "mcp.json")
    registry.add(
        EndpointRecord(
            name="remote",
            source="https://mcp.example/sse",
            transport="sse",
            command="npx",
            args=["--token", _CANARY],
        )
    )
    out = _lines(render_mcp(_deps(tmp_path, mcp=registry)))
    assert "remote" in out
    assert _CANARY not in out
    assert "--token" not in out


def test_render_config_masks_secret_value(tmp_path) -> None:
    """配置视图：密钥只出引用名 + 可解析结论。"""
    out = _lines(render_config(_deps(tmp_path)))
    assert "${CORE_DIAG_KEY}" in out
    assert _CANARY not in out


def test_render_notes_marks_pinned(tmp_path) -> None:
    store = NoteStore(path=tmp_path / "notes")
    store.create("alpha", title="甲")
    store.set_pinned("alpha", pinned=True, priority=3)
    out = _lines(render_notes(_deps(tmp_path, notes=store)))
    assert "alpha" in out
    assert "常驻" in out


def test_render_skills_lists_catalog_and_library(tmp_path) -> None:
    library = SkillLibrary(tmp_path / "skills.json")
    library.register(Skill(skill_id="skills.demo.one", description="演示"))
    out = _lines(render_skills(_deps(tmp_path, library=library)))
    assert "skills.demo.one" in out


def test_views_degrade_without_handles() -> None:
    """句柄缺失 ⇒ 视图输出用法提示而不是崩（TUI 里点开一张空表的体验）。"""
    empty = Deps()
    for view in (render_sessions, render_config, render_mcp, render_skills, render_notes):
        assert _lines(view(empty)).strip()


# ---- 红线：包边界 ----


def test_diagnostics_never_imports_runtime_or_ui() -> None:
    """`core.diagnostics` 是**只读诊断源**：不 import 组合根 `core.runtime`（硬红线），
    亦不 import `core.ui`（`ui` 反向引用它 —— 互相引用即成环）。"""
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "core" / "diagnostics"
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                name = node.module
            elif isinstance(node, ast.Import):
                name = ",".join(alias.name for alias in node.names)
            else:
                continue
            if "core.runtime" in name or "core.ui" in name:
                offenders.append(f"{path.name}:{node.lineno} {name}")
    assert not offenders, f"诊断包越界引用: {offenders}"


if __name__ == "__main__":  # pragma: no cover — 手工直跑
    raise SystemExit(pytest.main([__file__, "-q"]))
