"""core-profile 题词模板（骨架）测试（change 0142 / 账本 E85）。

规格 `core-profile/spec.md`「题词模板」SHALL 提供**可直接复制**的两级骨架文件；骨架的分区标题须与
运行时解析器逐字一致、分区非空 —— 否则复制后落 `SECTION_INVALID` 被**静默跳过**（用户难察觉）。
故本测试不再另写判据，直接以**解析器原文往返**为门禁。
"""

from __future__ import annotations

from pathlib import Path

from core.core_profile import SectionParser, Validator

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
_GLOBAL = _TEMPLATES / "Core.global.md"
_PROJECT = _TEMPLATES / "Core.project.md"
_MAX_LINES = 50  # 题词规范：篇幅受控（建议不超过 50 行）


def _parse(path: Path) -> tuple[list[str], list[str]]:
    """以骨架**原文**跑真实解析链，返回（分区 kind 序，告警列表）。"""
    validator = Validator()
    sections = validator.validate(SectionParser().parse(path.read_text(encoding="utf-8")))
    return [section.kind for section in sections], validator.warnings


def test_both_template_skeletons_exist() -> None:
    """两级骨架落在仓库 `templates/` 下（spec「题词模板」具名产出物）。"""
    assert _GLOBAL.is_file()
    assert _PROJECT.is_file()


def test_global_skeleton_carries_two_sections_only() -> None:
    """全局级骨架 = 宪法与全局规则 + 人格；「项目信息」属项目级，不得混入。"""
    text = _GLOBAL.read_text(encoding="utf-8")
    assert "## 宪法与全局规则" in text
    assert "## 人格" in text
    assert "## 项目信息" not in text


def test_global_skeleton_round_trips_clean_through_parser() -> None:
    """复制即用：原文解析出 constitution + personality，且**零** SECTION_INVALID 告警。"""
    kinds, warnings = _parse(_GLOBAL)
    assert kinds == ["constitution", "personality"]
    assert warnings == []


def test_project_skeleton_round_trips_clean_through_parser() -> None:
    """项目级骨架同理：解析出 project_info 且零告警（标题逐字、分区非空）。"""
    kinds, warnings = _parse(_PROJECT)
    assert kinds == ["project_info"]
    assert warnings == []


def test_skeletons_note_runtime_injection_channels() -> None:
    """各分区附注入说明注释，注明落向的运行时通道（spec 原文要求）。"""
    global_text = _GLOBAL.read_text(encoding="utf-8")
    assert "constitution:v1" in global_text
    assert "L0" in global_text
    assert "ContextEngine" in _PROJECT.read_text(encoding="utf-8")


def test_skeletons_are_bounded_in_length() -> None:
    """篇幅受控：两份骨架各自不超过题词规范建议的 50 行。"""
    for path in (_GLOBAL, _PROJECT):
        assert len(path.read_text(encoding="utf-8").splitlines()) <= _MAX_LINES
