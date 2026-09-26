"""两级 Core.md 加载器（GlobalProfileLoader / ProjectProfileLoader）。

全局级 ``~/.core/Core.md`` 承载人格 + 宪法与全局规则；项目级 ``<project>/Core.md``
承载项目信息（cwd 向上查找）。文件缺失静默降级返回空画像，不报错。

对应接口：doc/03-interfaces/core-profile-interface.md §3
"""

from __future__ import annotations

from pathlib import Path

from .models import CoreProfile
from .profile import SectionParser, Validator


class GlobalProfileLoader:
    """读取全局级 Core.md；文件缺失返回空画像，不报错。"""

    def __init__(
        self,
        path: str | Path = "~/.core/Core.md",
        parser: SectionParser | None = None,
        validator: Validator | None = None,
    ) -> None:
        self._path = Path(path).expanduser()
        self._parser = parser if parser is not None else SectionParser()
        self._validator = validator if validator is not None else Validator()

    def load(self) -> CoreProfile:
        if not self._path.is_file():
            return CoreProfile()  # 静默降级
        sections = self._validator.validate(
            self._parser.parse(self._path.read_text(encoding="utf-8"))
        )
        constitution: list[str] = []
        personality: list[str] = []
        for section in sections:
            if section.kind == "constitution":
                constitution.extend(section.lines)
            elif section.kind == "personality":
                personality.extend(section.lines)
        return CoreProfile(
            constitution=constitution, personality=personality, source=str(self._path)
        )


class ProjectProfileLoader:
    """从 cwd 向上查找项目级 Core.md，提取项目信息分区。"""

    def __init__(
        self,
        cwd: str | Path | None = None,
        parser: SectionParser | None = None,
        validator: Validator | None = None,
    ) -> None:
        self._cwd = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd()
        self._parser = parser if parser is not None else SectionParser()
        self._validator = validator if validator is not None else Validator()

    def find_upwards(self, cwd: str) -> str | None:
        """从 cwd 逐级向上查找 Core.md，返回最靠近的项目根文件路径；未命中返回 None。"""
        start = Path(cwd).expanduser().resolve()
        for directory in (start, *start.parents):
            candidate = directory / "Core.md"
            if candidate.is_file():
                return str(candidate)
        return None

    def load(self) -> CoreProfile:
        path = self.find_upwards(str(self._cwd))
        if path is None:
            return CoreProfile()  # 未命中：静默降级
        sections = self._validator.validate(
            self._parser.parse(Path(path).read_text(encoding="utf-8"))
        )
        project_info: list[str] = []
        for section in sections:
            if section.kind == "project_info":
                project_info.extend(section.lines)
        return CoreProfile(project_info=project_info, source=path)
