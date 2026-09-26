"""core-profile 单元测试（对齐规格场景 + M0 验收）。

覆盖 spec/core-profile 的场景：
- 两级 Core.md 加载（全局级人格/宪法 + 项目级项目信息）
- 双语义分区解析（宪法 → constitution:v1 coeffect、人格 → L0、项目信息 → 上下文）
- 项目级 cwd 向上查找 / 未命中静默降级
- 多级合并（项目级覆盖全局级）
- 校验容错（缺失静默、非法分区告警跳过）
- 宪法 coeffect 注入链路（→ CoeffectResolver 取用）
"""

from __future__ import annotations

from pathlib import Path

from core.core_profile import (
    AssembledProfile,
    CoreProfile,
    CoreProfileEngine,
    ErrorCode,
    GlobalProfileLoader,
    Merger,
    ProjectProfileLoader,
    Section,
    SectionParser,
    Validator,
)
from core.plugin_registry import CoeffectResolver

_GLOBAL_MD = """\
## 宪法与全局规则
> 本分区 → 注入 constitution:v1 coeffect
1. 必须保护用户隐私
2. 禁止伪造输出

## 人格
<!-- 人格分区 -->
- 身份：严谨的工程师助手
- 工作风格：先想后做
"""

_PROJECT_MD = """\
## 项目信息
- 项目：core-agent
- 技术栈：Python 3.11
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_section_parser_parses_three_kinds() -> None:
    raw = "## 宪法与全局规则\n1. 必须\n\n## 人格\n- 身份：x\n\n## 项目信息\n- 项目：y\n"
    sections = SectionParser().parse(raw)
    assert [s.kind for s in sections] == ["constitution", "personality", "project_info"]
    assert sections[0].lines == ["1. 必须"]
    assert sections[2].lines == ["- 项目：y"]


def test_section_parser_skips_annotations_and_marks_unknown() -> None:
    raw = "前言\n## 未知分区\n- 忽略\n## 人格\n- 身份：x\n> 注解\n<!-- 注释 -->\n"
    sections = SectionParser().parse(raw)
    assert [s.kind for s in sections] == ["unknown", "personality"]
    assert sections[1].lines == ["- 身份：x"]


def test_validator_skips_invalid_and_warns() -> None:
    sections = [
        Section(kind="constitution", lines=["1. 必须"]),
        Section(kind="unknown", lines=["- x"]),
        Section(kind="personality", lines=[]),
    ]
    validator = Validator()
    valid = validator.validate(sections)
    assert [s.kind for s in valid] == ["constitution"]
    assert len(validator.warnings) == 2  # noqa: PLR2004
    assert any("unknown" in w for w in validator.warnings)
    assert any("personality" in w for w in validator.warnings)
    assert all(ErrorCode.SECTION_INVALID.value in w for w in validator.warnings)


def test_global_loader_missing_silent(tmp_path) -> None:
    profile = GlobalProfileLoader(path=tmp_path / "nonexistent.md").load()
    assert profile.constitution == []
    assert profile.personality == []
    assert profile.source == ""


def test_global_loader_parses(tmp_path) -> None:
    path = _write(tmp_path / "Core.md", _GLOBAL_MD)
    profile = GlobalProfileLoader(path=path).load()
    assert profile.constitution == ["1. 必须保护用户隐私", "2. 禁止伪造输出"]
    assert profile.personality == ["- 身份：严谨的工程师助手", "- 工作风格：先想后做"]
    assert profile.source == str(path)


def test_project_find_upwards(tmp_path) -> None:
    root = tmp_path / "proj"
    sub = root / "a" / "b"
    sub.mkdir(parents=True)
    _write(root / "Core.md", _PROJECT_MD)
    loader = ProjectProfileLoader(cwd=sub)
    assert loader.find_upwards(str(sub)) == str(root / "Core.md")


def test_project_find_upwards_miss(tmp_path) -> None:
    loader = ProjectProfileLoader(cwd=tmp_path)
    assert loader.find_upwards(str(tmp_path)) is None


def test_project_loader_project_info(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    _write(root / "Core.md", _PROJECT_MD)
    profile = ProjectProfileLoader(cwd=root).load()
    assert profile.project_info == ["- 项目：core-agent", "- 技术栈：Python 3.11"]
    assert profile.constitution == []


def test_merger_project_overrides_global() -> None:
    global_p = CoreProfile(constitution=["g-rule"], personality=["g-persona"])
    project_p = CoreProfile(personality=["p-persona"], project_info=["p-info"])
    merged = Merger().merge(global_p, project_p)
    assert merged.constitution == ["g-rule"]  # 项目级无宪法 → 保留全局
    assert merged.personality == ["p-persona"]  # 项目级覆盖全局
    assert merged.project_info == ["p-info"]
    assert merged.source == "merged"


def test_engine_assemble(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    global_path = _write(tmp_path / "global.md", _GLOBAL_MD)
    _write(root / "Core.md", _PROJECT_MD)
    engine = CoreProfileEngine()
    engine.load_global(path=str(global_path))
    engine.load_project(cwd=str(root))
    assembled = engine.assemble()
    assert isinstance(assembled, AssembledProfile)
    assert assembled.coeffect["constitution:v1"] == ["1. 必须保护用户隐私", "2. 禁止伪造输出"]
    assert assembled.personality == ["- 身份：严谨的工程师助手", "- 工作风格：先想后做"]
    assert assembled.context == ["- 项目：core-agent", "- 技术栈：Python 3.11"]


def test_constitution_coeffect_injection_chain(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    global_path = _write(tmp_path / "global.md", _GLOBAL_MD)
    _write(root / "Core.md", _PROJECT_MD)
    engine = CoreProfileEngine()
    engine.load_global(path=str(global_path))
    engine.load_project(cwd=str(root))
    assembled = engine.assemble()
    resolver = CoeffectResolver()
    resolver.register("constitution:v1", assembled.coeffect["constitution:v1"])
    ctx = resolver.resolve(["constitution:v1"])
    assert ctx.get("constitution:v1") == ["1. 必须保护用户隐私", "2. 禁止伪造输出"]


def test_engine_warns_on_invalid_section(tmp_path) -> None:
    raw = "## 未知分区\n- 忽略\n## 人格\n- 身份：x\n"
    path = _write(tmp_path / "global.md", raw)
    engine = CoreProfileEngine()
    engine.load_global(path=str(path))
    assert any("unknown" in w for w in engine.warnings)


def test_error_codes() -> None:
    assert ErrorCode.PROFILE_MISSING.value == "PROFILE_MISSING"
    assert ErrorCode.SECTION_INVALID.value == "SECTION_INVALID"
