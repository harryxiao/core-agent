"""核心画像装配（CoreProfileEngine）。

启动时读全局级、载入项目时读项目级，合并两级画像后产出运行时注入单元：
宪法与全局规则 → ``constitution:v1`` coeffect，人格 → L0 记忆层，项目信息
→ ContextEngine 上下文。

对应接口：doc/03-interfaces/core-profile-interface.md §2
"""

from __future__ import annotations

from core.plugin_registry import CoeffectResolver

from .loader import GlobalProfileLoader, ProjectProfileLoader
from .models import AssembledProfile, CoreProfile
from .profile import Merger, SectionParser, Validator

_CONSTITUTION_COEFFECT = "constitution:v1"


class CoreProfileEngine:
    """两级 Core.md 的装配入口。"""

    def __init__(self, resolver: CoeffectResolver | None = None) -> None:
        self._parser = SectionParser()
        self._validator = Validator()
        self._merger = Merger()
        self._global: CoreProfile | None = None
        self._project: CoreProfile | None = None
        # 缺省自建；可传入上层共享的 resolver，把宪法 coeffect 桥接进同一注入通道
        self._resolver = resolver if resolver is not None else CoeffectResolver()

    @property
    def warnings(self) -> list[str]:
        """校验阶段记录的告警（SECTION_INVALID），供上层遥测/诊断取用。"""
        return self._validator.warnings

    @property
    def resolver(self) -> CoeffectResolver:
        """宪法 coeffect 注入的 resolver，供上层模块 ``resolve(["constitution:v1"])`` 取用。"""
        return self._resolver

    def load_global(self, path: str = "~/.core/Core.md") -> CoreProfile:
        """读取全局级 Core.md，解析双语义分区；缺失静默降级。"""
        self._global = GlobalProfileLoader(path, self._parser, self._validator).load()
        return self._global

    def load_project(self, cwd: str | None = None) -> CoreProfile:
        """读取项目级 Core.md（cwd 向上查找），注入项目信息。"""
        self._project = ProjectProfileLoader(cwd, self._parser, self._validator).load()
        return self._project

    def assemble(self) -> AssembledProfile:
        """合并全局级与项目级，产出运行时注入单元，并把宪法注册进 CoeffectResolver。"""
        global_p = self._global if self._global is not None else CoreProfile()
        project_p = self._project if self._project is not None else CoreProfile()
        merged = self._merger.merge(global_p, project_p)
        self._resolver.register(_CONSTITUTION_COEFFECT, merged.constitution)
        return AssembledProfile(
            coeffect={_CONSTITUTION_COEFFECT: merged.constitution},
            personality=merged.personality,
            context=merged.project_info,
        )
