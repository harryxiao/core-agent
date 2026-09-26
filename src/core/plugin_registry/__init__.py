"""插件注册表（L0 组合基底）。

一切皆插件：loop / 记忆 / 进化引擎 / 模型适配器都是本模块管理下的可替换
能力单元。本模块提供「插件即原子」的组合代数——注册、生命周期、可逆效应
追踪、coeffect 解析——但**不做任何业务**，是结晶经济闭环的原子载体。

对应规格：doc/openspec/specs/plugin-registry/spec.md
模块设计：doc/02-modules/plugin-registry.md
"""

from .coeffect_resolver import CoeffectMissing, CoeffectResolver, ResolvedContext, SecretRef
from .effect_tracker import Effect, EffectId, EffectTracker, RollbackReport
from .errors import DomainError, ErrorCode
from .installable import InstallableAsset, PluginInstaller, PluginKind, PluginSource
from .plugin import Plugin
from .registry import PluginRegistry, PluginState

__all__ = [
    "CoeffectMissing",
    "CoeffectResolver",
    "DomainError",
    "Effect",
    "EffectId",
    "EffectTracker",
    "ErrorCode",
    "InstallableAsset",
    "Plugin",
    "PluginInstaller",
    "PluginKind",
    "PluginRegistry",
    "PluginSource",
    "PluginState",
    "ResolvedContext",
    "RollbackReport",
    "SecretRef",
]
