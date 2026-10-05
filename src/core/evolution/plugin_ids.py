"""内部核心模块的**归因白名单**（evolution）。

`INTERNAL_PLUGIN_IDS` 是仓内 13 个内部核心模块的 `plugin_id` 集合，供 `Proposer` 判定
「诊断归因到的对象是**架构模块**还是**工具/外部能力**」——命中的候选 SHALL 为架构级
（`kind="plugin"`、`risk_level="high"`，强制人工审批），否则为技能库级。

**这不是 `PluginRegistry` 的成员名单**：本仓内部核心模块**未**纳入注册表（无注册表驱动的
`load`/`unload` 生命周期），故此处只声明**归因对象身份**，不承载装配 / 世代语义 ——
相关欠账见 `coding-plan/phase-21.md` §1.4②。

命名空间说明：`Trace.plugin_id` 是**归因对象 id**，两套命名空间（工具 id `tools.*` 与
内部核心模块 id）**互不相交**。新增内部核心模块（实现 `plugin_id` 的类）须同步登记 ——
有逐元素一致性用例守护（`tests/test_evolution_attribution.py`）。
"""

from __future__ import annotations

INTERNAL_PLUGIN_IDS: frozenset[str] = frozenset(
    {
        "composition.engine",
        "composition.packager",
        "composition.resolver",
        "evolution.collector",
        "evolution.diagnoser",
        "evolution.engine",
        "evolution.evaluator",
        "evolution.proposer",
        "evolution.validator",
        "evolution.worker",
        "im.gateway",
        "loop.default",
        "memory.store",
    }
)
