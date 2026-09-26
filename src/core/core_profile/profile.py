"""分区解析 / 校验 / 合并（SectionParser / Validator / Merger）。

按 ``## `` 分区标记把 Core.md 拆成三个语义分区；校验非法分区并告警跳过；
合并两级画像（项目级覆盖全局级）。分区标记格式非法（未知标题 / 空分区）
标记为 ``SECTION_INVALID``，加载其余合法分区，不阻断启动或载入。

对应接口：doc/03-interfaces/core-profile-interface.md §4 / §5 / §6
"""

from __future__ import annotations

from .errors import ErrorCode
from .models import CoreProfile, Section

# 分区标题 → 分区 kind；未识别的标题落入 "unknown" 供校验告警
_SECTION_HEADERS = {
    "## 宪法与全局规则": "constitution",
    "## 人格": "personality",
    "## 项目信息": "project_info",
}

_UNKNOWN = "unknown"

_VALID_KINDS = {"constitution", "personality", "project_info"}


def _is_content(line: str) -> bool:
    """是否是可注入的内容行：跳过空行 / HTML 注释 / 说明注解（``>``）。"""
    return bool(line) and not line.startswith("<!--") and not line.startswith(">")


class SectionParser:
    """按分区标记解析 Core.md，未识别内容忽略、未知标题标记为 ``unknown``。"""

    def parse(self, raw: str) -> list[Section]:
        sections: list[Section] = []
        current_kind: str | None = None
        current_lines: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                if current_kind is not None:
                    sections.append(Section(kind=current_kind, lines=current_lines))
                current_kind = _SECTION_HEADERS.get(stripped, _UNKNOWN)
                current_lines = []
            elif current_kind is not None and _is_content(stripped):
                current_lines.append(stripped)
        if current_kind is not None:
            sections.append(Section(kind=current_kind, lines=current_lines))
        return sections


class Validator:
    """格式校验：非法分区（未知 kind / 空内容）告警并跳过，返回合法分区。"""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def validate(self, sections: list[Section]) -> list[Section]:
        valid: list[Section] = []
        for section in sections:
            if section.kind in _VALID_KINDS and section.lines:
                valid.append(section)
            else:
                self.warnings.append(f"{ErrorCode.SECTION_INVALID.value}: {section.kind}")
        return valid


class Merger:
    """合并两级画像：项目级覆盖全局级同名分区，source 标记为 ``merged``。"""

    def merge(self, global_p: CoreProfile, project_p: CoreProfile) -> CoreProfile:
        return CoreProfile(
            constitution=project_p.constitution or global_p.constitution,
            personality=project_p.personality or global_p.personality,
            project_info=project_p.project_info or global_p.project_info,
            source="merged",
        )
