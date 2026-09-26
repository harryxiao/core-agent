"""插件统一契约（L0 Plugin Protocol）。

把 ``doc/03-interfaces/plugin-registry-interface.md`` §1 的四要素契约提炼为
``typing.Protocol``：``plugin_id`` / ``generation`` / ``schema`` / ``coeffects``
四字段 + ``load`` / ``unload`` / ``check`` 三生命周期方法。所有插件
（loop / 记忆 / 进化 / 工具 / 模型适配器）都必须满足本契约。

依赖解析（规格「依赖满足 / 循环依赖检测」场景）由注册表读取插件可选的
``deps`` 属性完成（见 ``registry.py``），不在本 Protocol 内强制声明，
保持与接口文档四要素契约一致。

对应规格：doc/openspec/specs/plugin-registry/spec.md
接口契约：doc/03-interfaces/plugin-registry-interface.md
"""

from __future__ import annotations

from typing import Any, Protocol


class Plugin(Protocol):
    """插件统一协议：四要素 + 生命周期。

    任何可替换能力单元（原子工具、记忆后端、模型适配器、loop 策略……）
    均需满足本结构契约，方能被 :class:`~plugin_registry.registry.PluginRegistry`
    安全地装载、运行与卸载。
    """

    plugin_id: str
    generation: int
    schema: dict[str, Any]
    coeffects: list[str]

    def load(self) -> None:
        """实例化并加载插件，注册其能力与运行时资源。"""
        ...

    def unload(self) -> None:
        """卸载插件并释放资源（引用 / 定时器 / 文件句柄全部回收）。"""
        ...

    def check(self) -> bool:
        """自检：声明（schema / coeffects）与实现是否一致。"""
        ...
